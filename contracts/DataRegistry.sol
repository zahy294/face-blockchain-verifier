// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

/**
 * @title DataRegistry
 * @dev EVM verification layer for on-chain data fingerprint notarization and verification.
 */
contract DataRegistry {
    struct Record {
        bool exists;
        address submitter;
        uint256 timestamp;
        string metadataUri;
    }

    mapping(bytes32 => Record) private records;

    event DataRecorded(bytes32 indexed dataHash, address indexed submitter, uint256 timestamp);

    error RecordAlreadyExists(bytes32 dataHash);

    /**
     * @notice Stores a notarized data record on-chain.
     * @param dataHash The keccak256 or SHA-256 32-byte hash fingerprint of the data.
     * @param metadataUri URI pointing to additional off-chain metadata (e.g., IPFS, HTTPS).
     */
    function recordData(bytes32 dataHash, string calldata metadataUri) external {
        if (records[dataHash].exists) {
            revert RecordAlreadyExists(dataHash);
        }

        records[dataHash] = Record({
            exists: true,
            submitter: msg.sender,
            timestamp: block.timestamp,
            metadataUri: metadataUri
        });

        emit DataRecorded(dataHash, msg.sender, block.timestamp);
    }

    /**
     * @notice Verifies whether a data fingerprint is registered and returns its record details.
     * @param dataHash The 32-byte hash fingerprint of the data to verify.
     * @return exists True if the record exists, false otherwise.
     * @return submitter The address that notarized the record.
     * @return timestamp The block timestamp when the record was notarized.
     * @return metadataUri The metadata URI associated with the record.
     */
    function verifyData(bytes32 dataHash)
        external
        view
        returns (
            bool exists,
            address submitter,
            uint256 timestamp,
            string memory metadataUri
        )
    {
        Record memory record = records[dataHash];
        return (record.exists, record.submitter, record.timestamp, record.metadataUri);
    }
}
