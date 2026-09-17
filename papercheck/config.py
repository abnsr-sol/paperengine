"""PaperEngine configuration file support.

Loads persistent settings from papercheck.toml (or .papercheck.yml) in the
current directory or home directory. Settings include default venue, standard,
ignored findings, and online API keys.

Format: TOML (stdlib tomllib in Python 3.11+; fallback to tomli or manual parse)

Example papercheck.toml:
```toml
[defaults]
venue = "ieee_conference"
standard = "international"
format = "html"
online = false

[ignore]
# Findings to suppress (category|title pattern)
patterns = [
    "Structure|No corresponding-author email",
    "Language|Filler phrases",
]

[api_keys]
# Optional API keys for enhanced lookups
openalex = ""
semantic_scholar = ""

[behavior]
# Engine-specific settings
max_online_checks = 10
word_count_gate = 200
```
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Any

# Configuration file names (searched in order)
_CONFIG_NAMES = ["papercheck.toml", ".papercheck.toml", ".papercheck.yml"]

# Default configuration
DEFAULTS: Dict[str, Any] = {
    "venue": "generic",
    "standard": "international",
    "format": "console",
    "online": False,
    "ignore_patterns": [],
    "max_online_checks": 10,
    "word_count_gate": 200,
}


def _find_config_file() -> Optional[str]:
    """Find the configuration file in current dir or home dir."""
    search_dirs = [
        os.getcwd(),
        os.path.expanduser("~"),
    ]
    for d in search_dirs:
        for name in _CONFIG_NAMES:
            path = os.path.join(d, name)
            if os.path.isfile(path):
                return path
    return None


def _parse_toml_simple(text: str) -> Dict[str, Any]:
    """Minimal TOML parser for configuration files.
    
    Handles nested sections, strings, booleans, integers, and arrays.
    Does NOT handle: inline tables, multiline strings, datetime, hex.
    Good enough for configuration files.
    """
    result: Dict[str, Any] = {}
    current_section = result
    
    for line in text.split("\n"):
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue
        
        # Section header: [section] or [section.subsection]
        section_match = re.match(r"^\[([^\]]+)\]$", line)
        if section_match:
            keys = section_match.group(1).split(".")
            current_section = result
            for key in keys:
                key = key.strip().strip('"').strip("'")
                if key not in current_section:
                    current_section[key] = {}
                current_section = current_section[key]
            continue
        
        # Key-value pair
        kv_match = re.match(r"^([^\s=]+)\s*=\s*(.+)$", line)
        if kv_match:
            key = kv_match.group(1).strip().strip('"').strip("'")
            value = kv_match.group(2).strip()
            
            # Parse value
            if value.startswith('"') and value.endswith('"'):
                # Double-quoted string
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                # Single-quoted string
                value = value[1:-1]
            elif value.startswith("[") and value.endswith("]"):
                # Array
                inner = value[1:-1].strip()
                if not inner:
                    value = []
                else:
                    items = []
                    for item in re.split(r",\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", inner):
                        item = item.strip()
                        if item.startswith('"') and item.endswith('"'):
                            items.append(item[1:-1])
                        elif item.startswith("'") and item.endswith("'"):
                            items.append(item[1:-1])
                        else:
                            items.append(item)
                    value = items
            elif value.lower() in ("true", "yes", "on"):
                value = True
            elif value.lower() in ("false", "no", "off"):
                value = False
            elif value.isdigit():
                value = int(value)
            else:
                try:
                    value = float(value)
                except ValueError:
                    pass
            
            current_section[key] = value
    
    return result


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from file. Returns merged config with defaults."""
    config = dict(DEFAULTS)
    
    if path is None:
        path = _find_config_file()
    
    if path is None:
        return config
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        
        # Try TOML parsing
        try:
            import tomllib
            file_config = tomllib.loads(text)
        except ImportError:
            try:
                import tomli
                file_config = tomli.loads(text)
            except ImportError:
                file_config = _parse_toml_simple(text)
        
        # Merge with defaults
        if "defaults" in file_config:
            config.update(file_config["defaults"])
        if "ignore" in file_config and "patterns" in file_config["ignore"]:
            config["ignore_patterns"] = file_config["ignore"]["patterns"]
        if "api_keys" in file_config:
            config["api_keys"] = file_config["api_keys"]
        if "behavior" in file_config:
            config.update(file_config["behavior"])
        
        return config
    
    except Exception:
        return config


def should_ignore_finding(finding_title: str, config: Dict[str, Any]) -> bool:
    """Check if a finding should be ignored based on config patterns."""
    patterns = config.get("ignore_patterns", [])
    for pattern in patterns:
        if re.search(pattern, finding_title, re.IGNORECASE):
            return True
    return False


# Export for CLI integration
__all__ = ["load_config", "should_ignore_finding", "DEFAULTS"]
