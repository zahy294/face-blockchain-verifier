"""Face Blockchain Verifier package."""

from .blockchain_notary import BlockchainNotary
from .exceptions import (
    APIKeyMissingError,
    BlockchainNotaryError,
    ContractExecutionError,
    FaceProcessingError,
    FaceVerificationError,
    InvalidImageError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    NoSocialMatchFoundError,
    RecordNotFoundError,
    RPCConnectionError,
    SocialSearchError,
)
from .face_processor import FaceCropResult, FaceProcessor
from .social_searcher import (
    SearchResult,
    SocialImageSearcher,
    SocialMatch,
    compute_canonical_hash,
)

__all__ = [
    "BlockchainNotary",
    "BlockchainNotaryError",
    "ContractExecutionError",
    "FaceCropResult",
    "FaceProcessingError",
    "FaceProcessor",
    "FaceVerificationError",
    "InvalidImageError",
    "MultipleFacesDetectedError",
    "NoFaceDetectedError",
    "NoSocialMatchFoundError",
    "RecordNotFoundError",
    "RPCConnectionError",
    "SearchResult",
    "SocialImageSearcher",
    "SocialMatch",
    "SocialSearchError",
    "APIKeyMissingError",
    "compute_canonical_hash",
]
