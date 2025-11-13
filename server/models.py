"""Database models."""
from sqlalchemy import Column, Integer, String
from database import Base


class Board(Base):
    """Board model representing a board in the system."""
    
    __tablename__ = "boards"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    
    def __repr__(self):
        return f"<Board(id={self.id}, name='{self.name}')>"
