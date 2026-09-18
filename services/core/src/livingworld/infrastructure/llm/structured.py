"""Strict local trust boundary. No HTTP, prompt changes, output repair or retries."""

import json
import math
from collections.abc import Mapping
from dataclasses import replace

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import NoSuchResource, Unresolvable
from referencing.jsonschema import DRAFT202012

from livingworld.application.llm import (
    FinishReason,
    LLMAttemptSummary,
    LLMErrorCode,
    LLMFailure,
    LLMResponse,
    StructuredFailureDetail,
    StructuredFailureReason,
    StructuredOutputRequest,
    ValidatedStructuredResult,
)

DIALECT = "https://json-schema.org/draft/2020-12/schema"


class InvalidStructuredSchema(ValueError):
    """Fixed diagnostic only; no schema, library error, rejected value or URI."""


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _deny_retrieval(uri):
    # No filesystem, HTTP, SDK resolver or library default remote retrieval.
    raise NoSuchResource(ref=uri)


def prepare_schema(request: StructuredOutputRequest) -> Draft202012Validator:
    """Check the explicit dialect and all local references before credential/HTTP IO."""
    schema = _plain(request.schema)
    invalid = False
    try:
        Draft202012Validator.check_schema(schema)
        resource = DRAFT202012.create_resource(schema)
        registry = Registry(retrieve=_deny_retrieval)
        resolver = registry.resolver_with_root(resource)
        pending = [(resource, resolver)]
        seen = set()
        while pending:
            current, scope = pending.pop()
            node = current.contents
            if id(node) in seen:
                continue
            seen.add(id(node))
            if isinstance(node, dict):
                if node.get("$schema", DIALECT) not in {DIALECT, DIALECT + "#"}:
                    invalid = True
                    break
                for keyword in ("$ref", "$dynamicRef"):
                    if keyword in node:
                        reference = node[keyword]
                        if not reference.startswith("#"):
                            invalid = True
                            break
                        resolved = scope.lookup(reference)
                        # A pointer may target ordinary annotation data. Once
                        # referenced, that target must itself be a valid schema.
                        Draft202012Validator.check_schema(resolved.contents)
                        pending.append(
                            (
                                DRAFT202012.create_resource(resolved.contents),
                                resolved.resolver,
                            )
                        )
                if invalid:
                    break
            for child in current.subresources():
                pending.append((child, scope.in_subresource(child)))
        validator = Draft202012Validator(schema, registry=registry, format_checker=None)
    except (SchemaError, Unresolvable, ValueError, TypeError, RecursionError):
        invalid = True
    # Do not expose library exceptions through __context__, including SchemaError.instance.
    if invalid:
        raise InvalidStructuredSchema("invalid_structured_schema")
    return validator


def _constant(_):
    raise ValueError("non_finite_json")


def _float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("non_finite_json")
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _path(parts):
    return tuple(
        part if type(part) is int and 0 <= part <= 2**31 - 1 else "*" for part in list(parts)[:16]
    )


def validate_text(
    request: StructuredOutputRequest,
    validator: Draft202012Validator,
    text: str,
) -> ValidatedStructuredResult | StructuredFailureDetail:
    """Parse exactly one JSON value; validation never fills defaults or coerces values."""
    if not text.strip():
        return StructuredFailureDetail(StructuredFailureReason.EMPTY_OUTPUT)
    invalid = False
    try:
        value = json.loads(
            text,
            parse_constant=_constant,
            parse_float=_float,
            object_pairs_hook=_object,
        )
    except (ValueError, RecursionError):
        invalid = True
    if invalid:
        return StructuredFailureDetail(StructuredFailureReason.JSON_PARSE_FAILED)
    try:
        # First error only: bounded output; never retain ValidationError or its context tree.
        error = next(validator.iter_errors(value), None)
        if error is not None:
            return StructuredFailureDetail(
                StructuredFailureReason.SCHEMA_VALIDATION_FAILED,
                _path(error.absolute_path),
                _path(error.absolute_schema_path),
                error.validator,
            )
    except (Unresolvable, RecursionError):
        return StructuredFailureDetail(StructuredFailureReason.SCHEMA_VALIDATION_FAILED)
    return ValidatedStructuredResult(request.schema_name, value)


def process_structured(
    request: StructuredOutputRequest,
    validator: Draft202012Validator,
    response: LLMResponse,
) -> LLMResponse | LLMFailure:
    if response.finish_reason is FinishReason.REFUSAL:
        return response
    if response.finish_reason is FinishReason.OUTPUT_LIMIT:
        result = StructuredFailureDetail(StructuredFailureReason.OUTPUT_TRUNCATED)
    else:
        result = validate_text(request, validator, response.text)
    if isinstance(result, StructuredFailureDetail):
        return LLMFailure(
            LLMErrorCode.STRUCTURED_OUTPUT_FAILED,
            response.invocation_id,
            # No provider diagnostics: unknown codes/IDs may reflect private content.
            attempt=LLMAttemptSummary(
                response.model_used,
                response.usage,
                response.finish_reason,
                response.latency_ms,
                response.processing_tier,
            ),
            structured_detail=result,
        )
    return replace(response, structured_result=result)
