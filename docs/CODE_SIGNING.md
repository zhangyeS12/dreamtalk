# Code signing policy

Status: application preparation for SignPath Foundation, not yet approved. No publicly released dreamtalk executable currently carries a SignPath Foundation Windows signature. The existing Tauri updater signature verifies update integrity and does not identify a Windows publisher.

## Requested service

dreamtalk plans to apply for the free open-source SignPath.io subscription **and** signing with a certificate issued to SignPath Foundation. It is not a bring-your-own-certificate application.

If accepted, the attribution will be: “Free code signing provided by SignPath.io, certificate by SignPath Foundation”. This is a planned arrangement, not a claim that the Foundation already endorses this project.

## Proposed responsibilities

- Repository owner and proposed signing approver: [zhangyeS12](https://github.com/zhangyeS12).
- The repository owner maintains and reviews the project. External contributions require review before inclusion in a release.
- Production signing requests require explicit human approval. An automated build or coding assistant cannot approve a release on the owner's behalf.
- All participating maintainers must enable multi-factor authentication on GitHub and SignPath before signing is enabled. This requirement has not been verified for the owner's accounts by the assistant.

## Build and artifact policy

The project has GitHub Actions continuous integration. Current public Windows installers were produced locally; the verifiable GitHub-hosted release build and SignPath integration are not implemented yet. Existing local installers must not be represented as GitHub-built signing candidates.

Planned signing candidates are the project's own Windows desktop executable, Core executable, project-owned helper executable, and installer. Third-party binaries retain their own identity and licenses; they are not signed as project-authored code. Optional speech/vision weights and local environments are separate from the installer.

Signed artifacts must correspond to a reviewed source revision and approved version. Product metadata, installed binary bytes, package hashes, timestamped Windows signatures, and the final Tauri update signature must agree. Signing is followed by static verification; modified artifacts require a new verification/signing pass. Existing updater trust keys must not be replaced as a shortcut for adding Windows publisher signing.

The owner will publish the approved policy and attribution on the download pages before distributing Foundation-signed releases. Approval, signing availability, and Windows reputation are separate matters; this document does not guarantee an application will be accepted or that every SmartScreen prompt will disappear.

## Privacy

See [Privacy information](PRIVACY.md). Signing artifacts must exclude user saves, API keys, personal configuration, private exports, and private reference media.

## Sources

- [SignPath Foundation conditions](https://signpath.org/terms).
- [Official application](https://signpath.org/apply).
- [GitHub build provenance and signing integration](https://docs.signpath.io/trusted-build-systems/github).
