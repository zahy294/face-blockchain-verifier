// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title FaceNotary
 * @dev Decentralized immutable registry for face identity & social post integrity fingerprints.
 */
contract FaceNotary {
    struct NotaryRecord {
        bytes32 fingerprint;
        address submitter;
        uint256 timestamp;
        string metadataURI;
        bool exists;
    }

    // Mapping from canonical Keccak-256 fingerprint to notarized record
    mapping(bytes32 => NotaryRecord) private records;

    // Events
    event FingerprintNotarized(
        bytes32 indexed fingerprint,
        address indexed submitter,
        uint256 timestamp,
        string metadataURI
    );

    error AlreadyNotarized(bytes32 fingerprint);
    error RecordNotFound(bytes32 fingerprint);

    /**
     * @notice Notarizes a canonical 32-byte fingerprint with optional metadata.
     * @param fingerprint 32-byte Keccak-256 digest linking face hash + platform + URL.
     * @param metadataURI URI/IPFS link or descriptor of the notarized record.
     */
    function notarize(bytes32 fingerprint, string calldata metadataURI) external {
        if (records[fingerprint].exists) {
            revert AlreadyNotarized(fingerprint);
        }

        records[fingerprint] = NotaryRecord({
            fingerprint: fingerprint,
            submitter: msg.sender,
            timestamp: block.timestamp,
            metadataURI: metadataURI,
            exists: true
        });

        emit FingerprintNotarized(fingerprint, msg.sender, block.timestamp, metadataURI);
    }

    /**
     * @notice Verifies whether a fingerprint exists on-chain and returns record details.
     * @param fingerprint 32-byte Keccak-256 hash.
     */
    function verify(bytes32 fingerprint)
        external
        view
        returns (
            bool exists,
            uint256 timestamp,
            address submitter,
            string memory metadataURI
        )
    {
        NotaryRecord memory record = records[fingerprint];
        return (record.exists, record.timestamp, record.submitter, record.metadataURI);
    }
}
