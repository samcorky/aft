"""Database models."""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
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
    archived = Column(Boolean, nullable=False, default=False, index=True)
    
    # Relationship to column
    column = relationship("BoardColumn", back_populates="cards")
    
    # Relationship to checklist items
    checklist_items = relationship("ChecklistItem", back_populates="card", cascade="all, delete-orphan", order_by="ChecklistItem.order")
    
    # Relationship to comments (newest first)
    comments = relationship("Comment", back_populates="card", cascade="all, delete-orphan", order_by="Comment.order.desc()")
    
    def __repr__(self):
        return f"<Card(id={self.id}, column_id={self.column_id}, title='{self.title}', order={self.order})>"


class ChecklistItem(Base):
    """ChecklistItem model representing a checklist item within a card."""
    
    __tablename__ = "checklist_items"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    card_id = Column(Integer, ForeignKey('cards.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    checked = Column(Boolean, nullable=False, default=False)
    order = Column(Integer, nullable=False, default=0)
    
    # Relationship to card
    card = relationship("Card", back_populates="checklist_items")
    
    def __repr__(self):
        return f"<ChecklistItem(id={self.id}, card_id={self.card_id}, name='{self.name}', checked={self.checked}, order={self.order})>"


class Setting(Base):
    """Setting model for storing application settings."""
    
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column("key", String(255), nullable=False, unique=True, index=True)  # 'key' is a MySQL reserved word
    value = Column("value", Text, nullable=True)  # Quote for consistency
    
    def __repr__(self):
        return f"<Setting(id={self.id}, key='{self.key}')>"


class Comment(Base):
    """Comment model representing a journal comment on a card."""
    
    __tablename__ = "comments"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    card_id = Column(Integer, ForeignKey('cards.id', ondelete='CASCADE'), nullable=False, index=True)
    comment = Column(Text, nullable=False)  # Large text field for comments
    order = Column(Integer, nullable=False, index=True)  # Immutable order to preserve history
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    # Relationship to card
    card = relationship("Card", back_populates="comments")
    
    def __repr__(self):
        return f"<Comment(id={self.id}, card_id={self.card_id}, order={self.order})>"


class Notification(Base):
    """Notification model representing user notifications."""
    
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    subject = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    unread = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    
    def __repr__(self):
        return f"<Notification(id={self.id}, subject='{self.subject}', unread={self.unread})>"
