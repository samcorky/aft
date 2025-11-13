"""Database models."""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class Board(Base):
    """Board model representing a board in the system."""
    
    __tablename__ = "boards"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Relationship to columns
    columns = relationship("BoardColumn", back_populates="board", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Board(id={self.id}, name='{self.name}')>"


class BoardColumn(Base):
    """Column model representing a column within a board."""
    
    __tablename__ = "columns"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    board_id = Column(Integer, ForeignKey('boards.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    order = Column(Integer, nullable=False, default=0)
    
    # Relationship to board
    board = relationship("Board", back_populates="columns")
    
    # Relationship to cards
    cards = relationship("Card", back_populates="column", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<BoardColumn(id={self.id}, board_id={self.board_id}, name='{self.name}', order={self.order})>"


class Card(Base):
    """Card model representing a task card within a column."""
    
    __tablename__ = "cards"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    column_id = Column(Integer, ForeignKey('columns.id', ondelete='CASCADE'), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(String(2000), nullable=True)
    order = Column(Integer, nullable=False, default=0)
    
    # Relationship to column
    column = relationship("BoardColumn", back_populates="cards")
    
    def __repr__(self):
        return f"<Card(id={self.id}, column_id={self.column_id}, title='{self.title}', order={self.order})>"
