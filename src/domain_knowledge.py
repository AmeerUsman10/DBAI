"""
Domain Knowledge Module for DBAI
Stores learned entities, aliases, and business context
Build 30 - Phase 1
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from src.utils.atomic_write import atomic_write_json, atomic_read_json

logger = logging.getLogger(__name__)

# =============================================================================
# ENTITY MODEL
# =============================================================================

class DomainEntity:
    """Represents a learned domain entity with aliases"""
    
    def __init__(
        self,
        canonical_name: str,
        entity_type: str,
        aliases: Optional[List[str]] = None,
        description: str = "",
        sql_value: str = "",
        table_name: str = "",
        column_name: str = "",
        created_at: Optional[str] = None,
        last_matched: Optional[str] = None,
        match_count: int = 0,
        confidence: float = 1.0,
        source: str = "manual"
    ):
        self.canonical_name = canonical_name
        self.entity_type = entity_type  # "customer", "product", "location", etc.
        self.aliases = aliases or []
        self.description = description
        self.sql_value = sql_value or canonical_name  # Value to use in SQL
        self.table_name = table_name
        self.column_name = column_name
        self.created_at = created_at or datetime.now().isoformat()
        self.last_matched = last_matched
        self.match_count = match_count
        self.confidence = confidence
        self.source = source  # "manual", "learned", "imported"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage"""
        return {
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "aliases": self.aliases,
            "description": self.description,
            "sql_value": self.sql_value,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "created_at": self.created_at,
            "last_matched": self.last_matched,
            "match_count": self.match_count,
            "confidence": self.confidence,
            "source": self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainEntity":
        """Create from dictionary"""
        return cls(
            canonical_name=data.get("canonical_name", ""),
            entity_type=data.get("entity_type", "unknown"),
            aliases=data.get("aliases", []),
            description=data.get("description", ""),
            sql_value=data.get("sql_value", ""),
            table_name=data.get("table_name", ""),
            column_name=data.get("column_name", ""),
            created_at=data.get("created_at"),
            last_matched=data.get("last_matched"),
            match_count=data.get("match_count", 0),
            confidence=data.get("confidence", 1.0),
            source=data.get("source", "manual")
        )
    
    def matches(self, text: str) -> bool:
        """
        Check if text matches this entity (case-insensitive substring).
        
        Args:
            text: Text to check
            
        Returns:
            True if text matches canonical name or any alias
        """
        text_lower = text.lower()
        
        # Check canonical name
        if self.canonical_name.lower() in text_lower:
            return True
        
        # Check aliases
        for alias in self.aliases:
            if alias.lower() in text_lower:
                return True
        
        return False
    
    def add_alias(self, alias: str) -> bool:
        """
        Add a new alias if not already present.
        
        Args:
            alias: Alias to add
            
        Returns:
            True if alias was added
        """
        alias_lower = alias.lower()
        existing_lower = [a.lower() for a in self.aliases]
        
        if alias_lower not in existing_lower and alias_lower != self.canonical_name.lower():
            self.aliases.append(alias)
            return True
        return False


# =============================================================================
# DOMAIN KNOWLEDGE MANAGER
# =============================================================================

class DomainKnowledgeManager:
    """
    Manages domain knowledge entities.
    Handles storage, lookup, and alias resolution.
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._storage_path = Path(__file__).parent.parent / "cache" / "domain_knowledge.json"
        self._entities: Dict[str, DomainEntity] = {}  # key: canonical_name.lower()
        self._alias_index: Dict[str, str] = {}  # alias.lower() -> canonical_name
        self._load_entities()
        self._initialized = True
        
        logger.info("DomainKnowledgeManager initialized")
    
    def _load_entities(self) -> None:
        """Load entities from storage"""
        if not self._storage_path.exists():
            self._entities = {}
            self._alias_index = {}
            return
        
        try:
            data = atomic_read_json(self._storage_path, default={"entities": {}}) or {"entities": {}}
            self._entities = {}
            self._alias_index = {}
            for key, entity_data in data.get("entities", {}).items():
                entity = DomainEntity.from_dict(entity_data)
                self._entities[key] = entity
                self._alias_index[entity.canonical_name.lower()] = entity.canonical_name
                for alias in entity.aliases:
                    self._alias_index[alias.lower()] = entity.canonical_name
            logger.info(f"Loaded {len(self._entities)} domain entities")
        except Exception as e:
            logger.error(f"Failed to load domain knowledge: {e}")
            self._entities = {}
            self._alias_index = {}
    
    def _save_entities(self) -> bool:
        """Save entities to storage"""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "entities": {key: entity.to_dict() for key, entity in self._entities.items()}
            }
            atomic_write_json(self._storage_path, data)
            return True
        except Exception as e:
            logger.error(f"Failed to save domain knowledge: {e}")
            return False
    
    def _rebuild_alias_index(self) -> None:
        """Rebuild the alias index from entities"""
        self._alias_index = {}
        for entity in self._entities.values():
            self._alias_index[entity.canonical_name.lower()] = entity.canonical_name
            for alias in entity.aliases:
                self._alias_index[alias.lower()] = entity.canonical_name
    
    def add_entity(self, entity: DomainEntity) -> Tuple[bool, str]:
        """
        Add a new domain entity.
        
        Args:
            entity: Entity to add
            
        Returns:
            Tuple of (success, message)
        """
        key = entity.canonical_name.lower()
        
        if key in self._entities:
            return False, f"Entity '{entity.canonical_name}' already exists"
        
        self._entities[key] = entity
        
        # Update alias index
        self._alias_index[key] = entity.canonical_name
        for alias in entity.aliases:
            self._alias_index[alias.lower()] = entity.canonical_name
        
        if self._save_entities():
            logger.info(f"Entity added: {entity.canonical_name}")
            return True, f"Entity '{entity.canonical_name}' added"
        else:
            return False, "Failed to save entity"
    
    def update_entity(
        self,
        canonical_name: str,
        updates: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Update an existing entity.
        
        Args:
            canonical_name: Canonical name of entity to update
            updates: Dictionary of fields to update
            
        Returns:
            Tuple of (success, message)
        """
        key = canonical_name.lower()
        
        if key not in self._entities:
            return False, f"Entity not found: {canonical_name}"
        
        entity = self._entities[key]
        
        for field, value in updates.items():
            if hasattr(entity, field):
                setattr(entity, field, value)
        
        self._rebuild_alias_index()
        
        if self._save_entities():
            return True, "Entity updated"
        else:
            return False, "Failed to save entity"
    
    def delete_entity(self, canonical_name: str) -> Tuple[bool, str]:
        """Delete an entity"""
        key = canonical_name.lower()
        
        if key not in self._entities:
            return False, f"Entity not found: {canonical_name}"
        
        del self._entities[key]
        self._rebuild_alias_index()
        
        if self._save_entities():
            return True, "Entity deleted"
        else:
            return False, "Failed to delete entity"
    
    def get_entity(self, name: str) -> Optional[DomainEntity]:
        """
        Get entity by canonical name or alias.
        
        Args:
            name: Canonical name or alias
            
        Returns:
            Entity if found, else None
        """
        # Check alias index first
        canonical = self._alias_index.get(name.lower())
        if canonical:
            return self._entities.get(canonical.lower())
        return None
    
    def get_all_entities(
        self,
        entity_type: Optional[str] = None
    ) -> List[DomainEntity]:
        """
        Get all entities with optional type filtering.
        
        Args:
            entity_type: Filter by type, or None for all
            
        Returns:
            List of entities
        """
        entities = list(self._entities.values())
        
        if entity_type:
            entities = [e for e in entities if e.entity_type == entity_type]
        
        return entities
    
    def get_entity_types(self) -> List[str]:
        """Get list of all entity types"""
        types = set(e.entity_type for e in self._entities.values())
        return sorted(types)
    
    def resolve_text(self, text: str) -> List[Tuple[str, DomainEntity]]:
        """
        Find all entity matches in text.
        
        Args:
            text: Text to search
            
        Returns:
            List of (matched_text, entity) tuples
        """
        matches = []
        text_lower = text.lower()
        
        for entity in self._entities.values():
            # Check canonical name
            if entity.canonical_name.lower() in text_lower:
                matches.append((entity.canonical_name, entity))
                entity.match_count += 1
                entity.last_matched = datetime.now().isoformat()
                continue
            
            # Check aliases
            for alias in entity.aliases:
                if alias.lower() in text_lower:
                    matches.append((alias, entity))
                    entity.match_count += 1
                    entity.last_matched = datetime.now().isoformat()
                    break
        
        if matches:
            self._save_entities()
        
        return matches
    
    def apply_to_question(self, question: str) -> Tuple[str, Dict[str, str]]:
        """
        Apply entity resolution to a question.
        Replaces aliases with canonical SQL values.
        
        Args:
            question: User's question
            
        Returns:
            Tuple of (modified_question, replacements_dict)
        """
        modified = question
        replacements = {}
        
        matches = self.resolve_text(question)
        
        for matched_text, entity in matches:
            # For SQL value replacement, we note it but don't modify the question
            # The LLM should use the SQL value when generating queries
            replacements[matched_text] = {
                "canonical": entity.canonical_name,
                "sql_value": entity.sql_value,
                "table": entity.table_name,
                "column": entity.column_name
            }
        
        return modified, replacements
    
    def add_alias(self, canonical_name: str, alias: str) -> Tuple[bool, str]:
        """
        Add an alias to an existing entity.
        
        Args:
            canonical_name: Canonical name of entity
            alias: New alias to add
            
        Returns:
            Tuple of (success, message)
        """
        entity = self.get_entity(canonical_name)
        
        if not entity:
            return False, f"Entity not found: {canonical_name}"
        
        # Check if alias conflicts with existing entity or alias
        if alias.lower() in self._alias_index:
            existing = self._alias_index[alias.lower()]
            if existing.lower() != canonical_name.lower():
                return False, f"Alias '{alias}' already used by '{existing}'"
        
        if entity.add_alias(alias):
            self._alias_index[alias.lower()] = entity.canonical_name
            if self._save_entities():
                return True, f"Alias '{alias}' added to '{canonical_name}'"
            else:
                return False, "Failed to save alias"
        else:
            return False, "Alias already exists"
    
    def remove_alias(self, canonical_name: str, alias: str) -> Tuple[bool, str]:
        """Remove an alias from an entity"""
        entity = self.get_entity(canonical_name)
        
        if not entity:
            return False, f"Entity not found: {canonical_name}"
        
        alias_lower = alias.lower()
        
        if alias_lower not in [a.lower() for a in entity.aliases]:
            return False, f"Alias '{alias}' not found"
        
        entity.aliases = [a for a in entity.aliases if a.lower() != alias_lower]
        
        if alias_lower in self._alias_index:
            del self._alias_index[alias_lower]
        
        if self._save_entities():
            return True, f"Alias '{alias}' removed"
        else:
            return False, "Failed to save changes"
    
    def learn_entity(
        self,
        canonical_name: str,
        entity_type: str,
        context: str = "",
        confidence: float = 0.8
    ) -> Tuple[bool, str]:
        """
        Learn a new entity from context (e.g., from query results).
        
        Args:
            canonical_name: Name of entity
            entity_type: Type of entity
            context: Context where entity was found
            confidence: Confidence score (0-1)
            
        Returns:
            Tuple of (success, message)
        """
        key = canonical_name.lower()
        
        if key in self._entities:
            # Entity exists, maybe update confidence
            entity = self._entities[key]
            entity.confidence = max(entity.confidence, confidence)
            self._save_entities()
            return True, f"Entity '{canonical_name}' already known"
        
        entity = DomainEntity(
            canonical_name=canonical_name,
            entity_type=entity_type,
            description=f"Learned from: {context[:100]}" if context else "",
            confidence=confidence,
            source="learned"
        )
        
        return self.add_entity(entity)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get domain knowledge statistics"""
        entities = list(self._entities.values())
        
        total = len(entities)
        by_type = {}
        for entity in entities:
            by_type[entity.entity_type] = by_type.get(entity.entity_type, 0) + 1
        
        total_aliases = sum(len(e.aliases) for e in entities)
        total_matches = sum(e.match_count for e in entities)
        
        # Top matched entities
        by_matches = sorted(entities, key=lambda e: e.match_count, reverse=True)[:5]
        top_matched = [
            {"name": e.canonical_name, "matches": e.match_count}
            for e in by_matches if e.match_count > 0
        ]
        
        return {
            "total_entities": total,
            "by_type": by_type,
            "total_aliases": total_aliases,
            "total_matches": total_matches,
            "top_matched": top_matched
        }
    
    def export_entities(self) -> List[Dict[str, Any]]:
        """Export all entities as a list of dicts"""
        return [e.to_dict() for e in self._entities.values()]
    
    def import_entities(
        self,
        entities_data: List[Dict[str, Any]],
        overwrite: bool = False
    ) -> Tuple[int, int]:
        """
        Import entities from a list of dicts.
        
        Args:
            entities_data: List of entity dictionaries
            overwrite: If True, overwrite existing entities
            
        Returns:
            Tuple of (added_count, skipped_count)
        """
        added = 0
        skipped = 0
        
        for data in entities_data:
            entity = DomainEntity.from_dict(data)
            key = entity.canonical_name.lower()
            
            if key in self._entities and not overwrite:
                skipped += 1
                continue
            
            self._entities[key] = entity
            added += 1
        
        self._rebuild_alias_index()
        self._save_entities()
        
        logger.info(f"Imported {added} entities, skipped {skipped}")
        return added, skipped


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_domain_manager() -> DomainKnowledgeManager:
    """Get the singleton DomainKnowledgeManager instance"""
    return DomainKnowledgeManager()


def resolve_entities(text: str) -> List[Dict[str, Any]]:
    """
    Find all known entities in text.
    
    Args:
        text: Text to search
        
    Returns:
        List of matched entity info dicts
    """
    manager = get_domain_manager()
    matches = manager.resolve_text(text)
    
    return [
        {
            "matched": matched_text,
            "canonical": entity.canonical_name,
            "type": entity.entity_type,
            "sql_value": entity.sql_value
        }
        for matched_text, entity in matches
    ]
