"""Enums and constants for Splunk app updater"""

from enum import Enum, auto
from typing import Optional


class UpdateStatus(str, Enum):
    """Status of an update in tracking"""
    PENDING = "pending"
    PUSHED = "pushed"
    MERGED = "merged"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
    def __str__(self) -> str:
        return self.value


class Environment(str, Enum):
    """Environment types"""
    PROD = "prod"
    NON_PROD = "non-prod"
    NONPROD = "nonprod"  # Alias
    SHARED = "shared"
    
    @classmethod
    def normalize(cls, value: str) -> 'Environment':
        """Normalize environment string to enum"""
        normalized = value.lower().strip()
        if normalized in ['prod', 'production']:
            return cls.PROD
        elif normalized in ['non-prod', 'nonprod', 'non_prod', 'dev', 'development']:
            return cls.NON_PROD
        elif normalized in ['shared']:
            return cls.SHARED
        raise ValueError(f"Unknown environment: {value}")
    
    def __str__(self) -> str:
        return self.value


class Component(str, Enum):
    """Splunk component types"""
    DS = "ds"  # Deployment Server (Universal Forwarders)
    HF = "hf"  # Heavy Forwarder
    SHC = "shc"  # Search Head Cluster
    CM = "cm"  # Cluster Manager
    
    @classmethod
    def from_string(cls, value: str) -> 'Component':
        """Convert string to Component enum"""
        component_map = {
            'ds': cls.DS,
            'deployment-server': cls.DS,
            'deployment_server': cls.DS,
            'hf': cls.HF,
            'heavy-forwarder': cls.HF,
            'heavy_forwarder': cls.HF,
            'shc': cls.SHC,
            'search-head': cls.SHC,
            'search_head': cls.SHC,
            'cm': cls.CM,
            'cluster-manager': cls.CM,
            'cluster_manager': cls.CM,
        }
        normalized = value.lower().strip()
        if normalized in component_map:
            return component_map[normalized]
        raise ValueError(f"Unknown component type: {value}")
    
    def __str__(self) -> str:
        return self.value


class DeploymentType(str, Enum):
    """Deployment types for file filtering"""
    FORWARDER = "forwarder"
    HEAVY_FORWARDER = "heavy_forwarder"
    SEARCHHEAD = "searchhead"
    INDEXER = "indexer"
    
    @classmethod
    def from_component(cls, component: Component) -> Optional['DeploymentType']:
        """Get deployment type from component"""
        mapping = {
            Component.DS: cls.FORWARDER,
            Component.HF: cls.HEAVY_FORWARDER,
            Component.SHC: cls.SEARCHHEAD,
            Component.CM: cls.INDEXER,
        }
        return mapping.get(component)
    
    def __str__(self) -> str:
        return self.value


class ArchiveType(str, Enum):
    """Supported archive types"""
    TARBALL = "tgz"
    ZIP = "zip"
    SPL = "spl"  # SPL is actually a tarball
    
    @classmethod
    def from_path(cls, path: str) -> 'ArchiveType':
        """Determine archive type from file path"""
        path_lower = path.lower()
        if path_lower.endswith(('.tgz', '.tar.gz', '.spl')):
            return cls.TARBALL
        elif path_lower.endswith('.zip'):
            return cls.ZIP
        raise ValueError(f"Unknown archive type: {path}")
    
    def __str__(self) -> str:
        return self.value
