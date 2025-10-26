"""
User model and SQLite database implementation.

This module provides:
1. User data model
2. Database connection and table creation
3. Basic CRUD operations
4. Timestamp tracking for ETags
"""

import sqlite3
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import os


@dataclass
class User:
    """User data model with timestamp tracking."""
    id: Optional[int] = None
    name: str = ""
    email: str = ""
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary."""
        data = asdict(self)
        # Convert timestamps to ISO format for JSON serialization
        if data.get('created_at'):
            data['created_at'] = datetime.fromtimestamp(data['created_at']).isoformat()
        if data.get('updated_at'):
            data['updated_at'] = datetime.fromtimestamp(data['updated_at']).isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """Create user from dictionary."""
        return cls(**data)


class UserDatabase:
    """
    SQLite database for user management.
    
    Provides CRUD operations with timestamp tracking for ETag support.
    """
    
    def __init__(self, db_path: str = "users.db"):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.connection = None
        self._initialize_database()
    
    def _initialize_database(self) -> None:
        """Create database and users table if they don't exist."""
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row  # Enable column access by name
        
        cursor = self.connection.cursor()
        
        # Create users table with timestamp columns
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        
        # Create index on email for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
        """)
        
        self.connection.commit()
        print(f"✅ Database initialized at {self.db_path}")
    
    def create_user(self, name: str, email: str) -> User:
        """
        Create a new user.
        
        Args:
            name: User's name
            email: User's email (must be unique)
            
        Returns:
            Created user with assigned ID and timestamps
            
        Raises:
            sqlite3.IntegrityError: If email already exists
        """
        cursor = self.connection.cursor()
        current_time = time.time()
        
        cursor.execute("""
            INSERT INTO users (name, email, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (name, email, current_time, current_time))
        
        self.connection.commit()
        
        user_id = cursor.lastrowid
        
        return User(
            id=user_id,
            name=name,
            email=email,
            created_at=current_time,
            updated_at=current_time
        )
    
    def get_user(self, user_id: int) -> Optional[User]:
        """
        Get user by ID.
        
        Args:
            user_id: User's ID
            
        Returns:
            User object if found, None otherwise
        """
        cursor = self.connection.cursor()
        
        cursor.execute("""
            SELECT id, name, email, created_at, updated_at
            FROM users
            WHERE id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        
        if row is None:
            return None
        
        return User(
            id=row['id'],
            name=row['name'],
            email=row['email'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[User]:
        """
        Get all users with pagination.
        
        Args:
            limit: Maximum number of users to return
            offset: Number of users to skip
            
        Returns:
            List of User objects
        """
        cursor = self.connection.cursor()
        
        cursor.execute("""
            SELECT id, name, email, created_at, updated_at
            FROM users
            ORDER BY id
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        rows = cursor.fetchall()
        
        return [
            User(
                id=row['id'],
                name=row['name'],
                email=row['email'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            for row in rows
        ]
    
    def update_user(self, user_id: int, name: Optional[str] = None, 
                   email: Optional[str] = None) -> Optional[User]:
        """
        Update user information.
        
        Args:
            user_id: User's ID
            name: New name (optional)
            email: New email (optional)
            
        Returns:
            Updated user if found, None otherwise
            
        Raises:
            sqlite3.IntegrityError: If new email already exists
        """
        # Get current user to check if exists
        user = self.get_user(user_id)
        if user is None:
            return None
        
        # Build update query dynamically
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        
        if email is not None:
            updates.append("email = ?")
            params.append(email)
        
        # Always update timestamp
        current_time = time.time()
        updates.append("updated_at = ?")
        params.append(current_time)
        
        # Add user_id to params for WHERE clause
        params.append(user_id)
        
        cursor = self.connection.cursor()
        
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        
        self.connection.commit()
        
        # Return updated user
        return self.get_user(user_id)
    
    def delete_user(self, user_id: int) -> bool:
        """
        Delete user.
        
        Args:
            user_id: User's ID
            
        Returns:
            True if user was deleted, False if not found
        """
        cursor = self.connection.cursor()
        
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        self.connection.commit()
        
        return cursor.rowcount > 0
    
    def count_users(self) -> int:
        """
        Get total number of users.
        
        Returns:
            Total user count
        """
        cursor = self.connection.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM users")
        
        row = cursor.fetchone()
        
        return row['count']
    
    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            print("📕 Database connection closed")
    
    def __del__(self):
        """Ensure connection is closed on cleanup."""
        self.close()
