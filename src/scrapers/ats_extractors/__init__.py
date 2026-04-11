from .greenhouse import extract_greenhouse
from .lever import extract_lever
from .teamtailor import extract_teamtailor
from .applied import extract_applied
from ._default_stub import extract_default

EXTRACTOR_MAP = {
    "greenhouse": extract_greenhouse,
    "lever": extract_lever,
    "teamtailor": extract_teamtailor,
    "applied": extract_applied,
}


def get_extractor(ats_type: str):
    return EXTRACTOR_MAP.get(ats_type, extract_default)
