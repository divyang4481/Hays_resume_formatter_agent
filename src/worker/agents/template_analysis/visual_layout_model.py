from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class VisualToken:
    token_id: str
    raw_token: str
    public_token: str
    token_kind: str
    mergefield_name: Optional[str] = None
    region_name: Optional[str] = None

@dataclass
class VisualCell:
    cell_id: str
    table_id: str
    row_index: int
    cell_index: int
    text: str
    tokens: List[VisualToken] = field(default_factory=list)
    grid_span: int = 1
    role: Optional[str] = None

@dataclass
class VisualRow:
    row_id: str
    table_id: str
    row_index: int
    cells: List[VisualCell] = field(default_factory=list)
    row_text: str = ""
    role: Optional[str] = None

@dataclass
class VisualTable:
    table_id: str
    table_index: int
    rows: List[VisualRow] = field(default_factory=list)
    region_type: Optional[str] = None
    heading: Optional[str] = None
    order_index: int = 0

@dataclass
class VisualBlock:
    block_id: str
    source: str
    page_index: Optional[int]
    order_index: int
    block_type: str
    text: str
    style_name: Optional[str] = None
    bbox: Optional[Dict[str, Any]] = None
    tokens: List[VisualToken] = field(default_factory=list)

@dataclass
class VisualPage:
    page_index: int
    blocks: List[VisualBlock] = field(default_factory=list)

@dataclass
class VisualRegion:
    region_id: str
    region_type: str
    heading: Optional[str] = None
    region_name: Optional[str] = None
    tables: List[str] = field(default_factory=list) # list of table_ids
    blocks: List[str] = field(default_factory=list) # list of block_ids
    is_instruction_only: bool = False
    render_action: Optional[str] = None

@dataclass
class VisualModel:
    pages: List[VisualPage] = field(default_factory=list)
    tables: List[VisualTable] = field(default_factory=list)
    blocks: List[VisualBlock] = field(default_factory=list)
    regions: List[VisualRegion] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
