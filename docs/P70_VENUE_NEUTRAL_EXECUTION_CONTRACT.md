# P70 Venue-neutral Execution Contract

P70 defines the canonical boundary shared by venue adapters:

- `ExternalVenueRuntimePackage`
- `VenueCredentialReference`
- `VenueSignerProtocol`
- `VenueSubmitTransport`
- `VenueOrderIntent`
- `VenueSubmitReceipt`
- `VenueStatusEvent`
- `VenueEvidenceBundle`

The core contracts contain no endpoint, authentication algorithm, credential
value, or venue-specific market mapping. Such details belong in a physically
separate venue adapter. P59-P68 remains a Binance reference implementation and
is not runtime eligible. Extended will implement these contracts in later
stages.

P70 does not enable runtime, network, signing, submit, cancellation, or evidence
promotion.
