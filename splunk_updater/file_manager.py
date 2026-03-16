"""File management for Splunk apps"""

import logging
import re
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from .models import DeploymentConfig
from .enums import ArchiveType, Component, DeploymentType

logger = logging.getLogger(__name__)


class AppFileManager:
    """Manages app files for different deployment types"""
    
    def __init__(self, deployment_config: DeploymentConfig):
        self.deployment_config = deployment_config
    
    def extract_archive(self, archive_path: Path, extract_to: Path) -> Optional[Path]:
        """Extract app archive (tar.gz, spl, or zip)"""
        try:
            extract_to.mkdir(parents=True, exist_ok=True)
            
            archive_type = ArchiveType.from_path(str(archive_path))
            if archive_type in (ArchiveType.TARBALL, ArchiveType.SPL):
                return self._extract_tarball(archive_path, extract_to)
            elif archive_type == ArchiveType.ZIP:
                return self._extract_zip(archive_path, extract_to)
            
        except ValueError:
            logger.error(f"Unsupported archive format: {archive_path.name}")
            return None
        except Exception as e:
            logger.error(f"Error extracting archive {archive_path}: {e}")
            return None
    
    @staticmethod
    def _extract_tarball(archive_path: Path, extract_to: Path) -> Optional[Path]:
        """Extract tarball archive with path traversal protection"""
        import sys
        with tarfile.open(archive_path, 'r:gz') as tar:
            # Security: Check for path traversal before extraction
            extract_to_resolved = extract_to.resolve()
            for member in tar.getmembers():
                member_path = (extract_to / member.name).resolve()
                if not str(member_path).startswith(str(extract_to_resolved)):
                    logger.error(f"Security: Blocked path traversal attempt in archive: {member.name}")
                    raise ValueError(f"Path traversal detected in archive: {member.name}")
            
            # Python 3.12+ requires filter= to avoid DeprecationWarning
            if sys.version_info >= (3, 12):
                tar.extractall(extract_to, filter='data')
            else:
                tar.extractall(extract_to)
            members = tar.getmembers()
            if members:
                root_dir = members[0].name.split('/')[0]
                return extract_to / root_dir
        return None
    
    @staticmethod
    def _extract_zip(archive_path: Path, extract_to: Path) -> Optional[Path]:
        """Extract zip archive with path traversal protection"""
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            # Security: Check for path traversal before extraction
            extract_to_resolved = extract_to.resolve()
            for name in zip_ref.namelist():
                member_path = (extract_to / name).resolve()
                if not str(member_path).startswith(str(extract_to_resolved)):
                    logger.error(f"Security: Blocked path traversal attempt in archive: {name}")
                    raise ValueError(f"Path traversal detected in archive: {name}")
            
            zip_ref.extractall(extract_to)
            names = zip_ref.namelist()
            if names:
                root_dir = names[0].split('/')[0]
                return extract_to / root_dir
        return None
    
    def copy_app(self, source_app_dir: Path, target_dir: Path, component: Optional[str] = None,
                 preserve_paths: Optional[List[str]] = None) -> bool:
        """
        Copy app to target directory, filtering files based on component type.
        
        Args:
            source_app_dir: Source app directory
            target_dir: Target directory (will be the app folder in the repo)
            component: Component type ('ds', 'shc', 'cm') - determines which files to include
            preserve_paths: List of relative paths within the app to preserve during update
                           (e.g., ['bin/custom_script.sh']). local/ is always preserved.
        """
        try:
            deployment_type = self._get_deployment_type(component)
            
            # Backup custom preserve paths before update
            custom_backups = self._backup_preserve_paths(target_dir, preserve_paths)
            
            if not deployment_type:
                result = self._copy_full_app(source_app_dir, target_dir)
            else:
                result = self._copy_filtered_app(source_app_dir, target_dir, deployment_type)
            
            # Restore custom preserve paths after update
            self._restore_preserve_paths(target_dir, custom_backups)
            
            return result
            
        except Exception as e:
            logger.error(f"Error copying app: {e}")
            return False
    
    @staticmethod
    def _get_deployment_type(component: Optional[str]) -> Optional[str]:
        """Map component to deployment type using the enum definitions"""
        if not component:
            return None
        try:
            comp = Component.from_string(component)
            dt = DeploymentType.from_component(comp)
            return str(dt) if dt else None
        except ValueError:
            return None
    
    def _copy_full_app(self, source_app_dir: Path, target_dir: Path) -> bool:
        """Copy app without component filtering (global excludes still apply)"""
        global_excludes = list(self.deployment_config.global_excludes)
        
        if global_excludes:
            logger.info(f"Copying {source_app_dir.name} (no component filtering, global excludes applied)")
        else:
            logger.info(f"Copying {source_app_dir.name} (no filtering)")
        
        local_backup = self._backup_local_folder(target_dir)
        splunkbase_id_backup = self._backup_splunkbase_id(target_dir)
        
        if target_dir.exists():
            shutil.rmtree(target_dir)
        
        if global_excludes:
            target_dir.mkdir(parents=True, exist_ok=True)
            self._copy_with_excludes(source_app_dir, target_dir, global_excludes)
        else:
            shutil.copytree(source_app_dir, target_dir)
        
        self._restore_local_folder(target_dir, local_backup)
        self._restore_splunkbase_id(target_dir, splunkbase_id_backup)
        
        return True
    
    def _copy_filtered_app(self, source_app_dir: Path, target_dir: Path, deployment_type: str) -> bool:
        """Copy app with component-based filtering"""
        excludes = self._get_excludes(deployment_type)
        
        logger.info(f"Copying {source_app_dir.name} for {deployment_type} - filtering applied")
        
        local_backup = self._backup_local_folder(target_dir)
        splunkbase_id_backup = self._backup_splunkbase_id(target_dir)
        
        # Remove and recreate target
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy files, excluding specified patterns
        self._copy_with_excludes(source_app_dir, target_dir, excludes)
        
        self._restore_local_folder(target_dir, local_backup)
        self._restore_splunkbase_id(target_dir, splunkbase_id_backup)
        
        logger.info(f"Copied app with filtering to {target_dir}")
        return True
    
    def _get_excludes(self, deployment_type: str) -> list:
        """Get exclude patterns for deployment type, combined with global excludes"""
        global_excludes = list(self.deployment_config.global_excludes)
        if deployment_type == 'indexer':
            return global_excludes + self.deployment_config.indexer_excludes
        elif deployment_type == 'searchhead':
            return global_excludes + self.deployment_config.searchhead_excludes
        elif deployment_type == 'forwarder':
            return global_excludes + self.deployment_config.forwarder_excludes
        elif deployment_type == 'heavy_forwarder':
            return global_excludes + self.deployment_config.heavy_forwarder_excludes
        return global_excludes
    
    def _copy_with_excludes(self, source_dir: Path, target_dir: Path, excludes: list):
        """Copy files while excluding patterns"""
        for item in source_dir.rglob('*'):
            if item.is_file():
                rel_path = item.relative_to(source_dir)
                
                # Check if this file should be excluded
                if not self._should_exclude(str(rel_path), excludes):
                    target_file = target_dir / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target_file)
                else:
                    logger.debug(f"Excluding {rel_path}")
    
    def _should_exclude(self, path: str, excludes: list) -> bool:
        """Check if path matches any exclusion pattern"""
        for exclude_pattern in excludes:
            if self._matches_pattern(path, exclude_pattern):
                return True
        return False
    
    @staticmethod
    def _matches_pattern(path: str, pattern: str) -> bool:
        """Check if path matches exclusion pattern"""
        path = path.replace('\\', '/')
        
        # Exact match
        if path == pattern:
            return True
        
        # Starts with pattern (for directory exclusions) — require path separator boundary
        if path.startswith(pattern + '/'):
            return True
        
        # Pattern matching
        if '*' in pattern:
            regex = pattern.replace('*', '.*')
            if re.match(regex, path):
                return True
        
        return False
    
    @staticmethod
    def _backup_preserve_paths(target_dir: Path, preserve_paths: Optional[List[str]]) -> Dict[str, Path]:
        """Backup custom files/folders that should be preserved during update
        
        Args:
            target_dir: The app directory being updated
            preserve_paths: List of relative paths to preserve (e.g., ['bin/custom_script.sh'])
        
        Returns:
            Dict mapping relative path -> backup location
        """
        backups = {}
        if not preserve_paths:
            return backups
        
        for rel_path in preserve_paths:
            source = target_dir / rel_path
            if not source.exists():
                logger.debug(f"Preserve path not found (skipping): {rel_path}")
                continue
            
            # Create backup in parent directory with unique name
            safe_name = rel_path.replace('/', '_').replace('\\', '_')
            backup_path = target_dir.parent / f".preserve_backup_{target_dir.name}_{safe_name}"
            
            try:
                if source.is_dir():
                    if backup_path.exists():
                        shutil.rmtree(backup_path)
                    shutil.copytree(source, backup_path)
                else:
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, backup_path)
                
                backups[rel_path] = backup_path
                logger.info(f"Preserved custom path: {rel_path}")
            except Exception as e:
                logger.warning(f"Could not backup preserve path {rel_path}: {e}")
        
        return backups
    
    @staticmethod
    def _restore_preserve_paths(target_dir: Path, backups: Dict[str, Path]):
        """Restore custom preserved files/folders after update
        
        Args:
            target_dir: The app directory that was updated
            backups: Dict from _backup_preserve_paths
        """
        for rel_path, backup_path in backups.items():
            if not backup_path.exists():
                continue
            
            target = target_dir / rel_path
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                
                if backup_path.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(backup_path, target)
                    shutil.rmtree(backup_path)
                else:
                    shutil.copy2(backup_path, target)
                    backup_path.unlink()
                
                logger.info(f"Restored preserved path: {rel_path}")
            except Exception as e:
                logger.warning(f"Could not restore preserve path {rel_path}: {e}")
    
    @staticmethod
    def _backup_local_folder(target_dir: Path) -> Optional[Path]:
        """Backup the local folder if it exists"""
        local_dir = target_dir / 'local'
        if not local_dir.exists():
            return None
        
        local_backup = target_dir.parent / f".local_backup_{target_dir.name}"
        if local_backup.exists():
            shutil.rmtree(local_backup)
        shutil.copytree(local_dir, local_backup)
        logger.info("Preserved local folder temporarily")
        return local_backup
    
    @staticmethod
    def _restore_local_folder(target_dir: Path, local_backup: Optional[Path]):
        """Restore the local folder from backup"""
        if not local_backup or not local_backup.exists():
            return
        
        target_local = target_dir / 'local'
        if target_local.exists():
            shutil.rmtree(target_local)
        shutil.copytree(local_backup, target_local)
        shutil.rmtree(local_backup)
        logger.info("Restored local folder")
    
    @staticmethod
    def _backup_splunkbase_id(target_dir: Path) -> Optional[dict]:
        """Backup Splunkbase ID from app.conf and splunkbase.manifest if they exist"""
        backup = {}
        
        # Check for splunkbase.manifest
        manifest_path = target_dir / 'splunkbase.manifest'
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    backup['splunkbase_manifest'] = f.read()
                logger.debug("Backed up splunkbase.manifest")
            except Exception as e:
                logger.debug(f"Could not backup splunkbase.manifest: {e}")
        
        # Check for Splunkbase ID in app.conf
        app_conf_path = target_dir / 'default' / 'app.conf'
        if app_conf_path.exists():
            try:
                with open(app_conf_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Check if app.conf contains Splunkbase ID
                    install_section = AppFileManager._extract_install_section(content)
                    if install_section and ('splunkbase_id' in install_section or 'id =' in install_section):
                        backup['app_conf_install_section'] = install_section
                        logger.debug("Backed up Splunkbase ID from app.conf")
            except Exception as e:
                logger.debug(f"Could not backup app.conf install section: {e}")
        
        return backup if backup else None
    
    @staticmethod
    def _extract_install_section(app_conf_content: str) -> Optional[str]:
        """Extract [install] section from app.conf"""
        lines = app_conf_content.split('\n')
        install_section = []
        in_install_section = False
        
        for line in lines:
            stripped = line.strip()
            if stripped == '[install]':
                in_install_section = True
                install_section.append(line)
            elif in_install_section:
                if stripped.startswith('['):
                    # New section started
                    break
                install_section.append(line)
        
        return '\n'.join(install_section) if install_section else None
    
    @staticmethod
    def _restore_splunkbase_id(target_dir: Path, backup: Optional[dict]):
        """Restore Splunkbase ID to app.conf and splunkbase.manifest from backup"""
        if not backup:
            return
        
        # Restore splunkbase.manifest
        if 'splunkbase_manifest' in backup:
            manifest_path = target_dir / 'splunkbase.manifest'
            try:
                with open(manifest_path, 'w', encoding='utf-8') as f:
                    f.write(backup['splunkbase_manifest'])
                logger.info("Restored splunkbase.manifest with Splunkbase ID")
            except Exception as e:
                logger.warning(f"Could not restore splunkbase.manifest: {e}")
        
        # Restore [install] section in app.conf
        if 'app_conf_install_section' in backup:
            app_conf_path = target_dir / 'default' / 'app.conf'
            if app_conf_path.exists():
                try:
                    with open(app_conf_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Remove existing [install] section if present
                    content = AppFileManager._remove_install_section(content)
                    
                    # Append backed up [install] section
                    if not content.endswith('\n'):
                        content += '\n'
                    content += '\n' + backup['app_conf_install_section']
                    
                    with open(app_conf_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.info("Restored Splunkbase ID to app.conf")
                except Exception as e:
                    logger.warning(f"Could not restore Splunkbase ID to app.conf: {e}")
    
    @staticmethod
    def _remove_install_section(app_conf_content: str) -> str:
        """Remove [install] section from app.conf"""
        lines = app_conf_content.split('\n')
        result = []
        in_install_section = False
        
        for line in lines:
            stripped = line.strip()
            if stripped == '[install]':
                in_install_section = True
                continue
            elif in_install_section and stripped.startswith('['):
                in_install_section = False
            
            if not in_install_section:
                result.append(line)
        
        return '\n'.join(result)
