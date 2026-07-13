# Package Boundary

- Package scope: `separate_external_runtime_package_only`
- Default runtime candidate inclusion: **false**
- Review package import permission: **false**
- Runner enabled: **false**
- Network calls enabled: **false**
- Signing enabled: **false**
- Submit enabled: **false**
- Concrete network transport included: **false**
- Concrete signer included: **false**
- Secret reader included: **false**
- Real endpoint execution enabled: **false**

All API key and secret values remain outside this package. Only metadata references and fingerprints are permitted.

## P61 Boundary

The P61 adapter may define and validate the external executor protocol, request descriptor, approval contract, activation contract, and redacted response contract. It must not bundle credential values, a credential reader, or a concrete enabled executor. The default runtime candidate must continue to exclude `external_runtime_packages/`. The real order submit endpoint `/fapi/v1/order` remains disabled.

## P62 Boundary

The P62 operator kit remains part of the separate external-runtime package and is excluded from the default runtime candidate. Its default policy is disabled. Concrete credential handling, signing, and network transport are not bundled. The only tested execution is a no-network fixture path; generated fixture evidence is not eligible for real P58/P7 progression.

## P63 Boundary

The P63 concrete executor orchestrator may be distributed only in the separate operator/external package. The default runtime candidate must exclude `external_runtime_packages/`. A real opaque credentialed sender, concrete signer, credential reader, or network transport must not be bundled in the review/default runtime package.

## P64 Subprocess Boundary

The package may include the P64 bridge implementation and validators, but it must not include the operator's concrete sender executable, credentials, secret files, signer implementation, or network transport. The concrete sender is installed separately and identified only by absolute path, SHA256, metadata reference, and redacted-output contract. The default runtime candidate must exclude the entire external runtime package.
