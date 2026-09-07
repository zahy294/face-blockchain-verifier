"""Custom exception hierarchy for Face Blockchain Verifier."""


class FaceVerificationError(Exception):
    """Base exception for all face blockchain verifier errors."""
    pass


class FaceProcessingError(FaceVerificationError):
    """Raised when face detection or image processing fails."""
    pass


class InvalidImageError(FaceProcessingError):
    """Raised when the input file is not a valid or readable image."""
    pass


class NoFaceDetectedError(FaceProcessingError):
    """Raised when no face is found in the provided image."""
    pass


class MultipleFacesDetectedError(FaceProcessingError):
    """Raised when multiple faces are detected and strict single face mode is enabled."""
    pass


class SocialSearchError(FaceVerificationError):
    """Raised when social image search fails."""
    pass


class APIKeyMissingError(SocialSearchError):
    """Raised when a required API key or service credential is missing."""
    pass


class NoSocialMatchFoundError(SocialSearchError):
    """Raised when reverse image search yields no social profile/post matches."""
    pass


class BlockchainNotaryError(FaceVerificationError):
    """Raised when blockchain notarization or query fails."""
    pass


class RPCConnectionError(BlockchainNotaryError):
    """Raised when the Ethereum RPC node cannot be reached."""
    pass


class ContractExecutionError(BlockchainNotaryError):
    """Raised when contract transaction or call fails."""
    pass


class RecordNotFoundError(BlockchainNotaryError):
    """Raised when a fingerprint is not found on-chain."""
    pass
