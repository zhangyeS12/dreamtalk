//! Separate speech ownership scope, backed by the shared registry implementation.

pub const REGISTRY: crate::scoped_credentials::CredentialDomain =
    crate::scoped_credentials::CredentialDomain::Speech;
