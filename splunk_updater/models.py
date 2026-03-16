"""Data models for Splunk app updater"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional


@dataclass
class SplunkApp:
    """Represents a Splunk app with version and deployment info
    
    Apps are filtered during deployment based on the repo's component type:
    - DS repos (component: ds) → forwarder-relevant files only
    - SHC repos (component: shc) → searchhead-relevant files only  
    - CM repos (component: cm) → indexer-relevant files only
    
    Apps maintain standard Splunk structure (no component subfolders).
    """
    name: str
    local_path: Path
    current_version: str
    splunkbase_id: Optional[str]
    deployment_types: List[str] = field(default_factory=list)  # Informational: ['indexer', 'searchhead', 'forwarder']
    latest_version: Optional[str] = None
    needs_update: bool = False
    environment: Optional[str] = None  # prod, non-prod, shared, etc.
    region: Optional[str] = None  # east, west, etc.
    component: Optional[str] = None  # ds, shc, cm - determines filtering rules for the repo
    repo_root: Optional[Path] = None  # Root path of the git repository
    
    # Runtime attributes set by updater during check_for_updates / update_app
    available_versions: List[str] = field(default_factory=list)
    needs_version_selection: bool = False
    current_version_unavailable: bool = False
    nonprod_version_unavailable: bool = False
    nonprod_version_requested: Optional[str] = None
    extracted_dir: Optional[Path] = None  # Set after download & extraction
    branch_name: Optional[str] = None  # Set after branch creation

    @property
    def instance_id(self) -> str:
        """Human-readable identifier including environment/region context.

        Example: ``"Splunk_TA_windows [non-prod] [east]"``
        """
        parts = [self.name]
        if self.environment:
            parts.append(f"[{self.environment}]")
        if self.region:
            parts.append(f"[{self.region}]")
        return " ".join(parts)

    def metadata_parts(self, *, labeled: bool = True) -> List[str]:
        """Return environment/region/component as display fragments.

        Args:
            labeled: If ``True`` (default), prefix each part with its label
                     (e.g. ``"Env: non-prod"``).  If ``False``, return the
                     raw values (e.g. ``"non-prod"``).
        """
        parts: List[str] = []
        if self.environment:
            parts.append(f"Env: {self.environment}" if labeled else self.environment)
        if self.region:
            parts.append(f"Region: {self.region}" if labeled else self.region)
        if self.component:
            parts.append(f"Component: {self.component}" if labeled else self.component)
        return parts


@dataclass
class DeploymentConfig:
    """Configuration for component-based deployment filtering
    
    Files are filtered based on the repo's component (ds/shc/cm), not within the app structure.
    """
    indexer_dirs: List[str]
    searchhead_dirs: List[str]
    forwarder_dirs: List[str]
    
    indexer_excludes: List[str]
    searchhead_excludes: List[str]
    forwarder_excludes: List[str]
    heavy_forwarder_excludes: List[str]
    global_excludes: List[str]
