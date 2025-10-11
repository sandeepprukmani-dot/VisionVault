import numpy as np
import faiss
import json
import os
from typing import List, Dict, Tuple, Optional
from openai import OpenAI


class VectorStore:
    """Vector store for semantic search using FAISS."""
    
    def __init__(self, dimension=1536, index_path='vector_index.faiss', 
                 metadata_path='vector_metadata.json'):
        self.dimension = dimension  # OpenAI embeddings are 1536 dimensions
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.index = None
        self.metadata = []  # Store task_ids corresponding to each vector
        
        # Initialize or load index
        self._load_or_create_index()
    
    def _load_or_create_index(self):
        """Load existing index or create a new one."""
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            print(f"Loading existing vector index from {self.index_path}")
            self.index = faiss.read_index(self.index_path)
            with open(self.metadata_path, 'r') as f:
                self.metadata = json.load(f)
        else:
            print("Creating new vector index")
            # Using IndexFlatL2 for simplicity - cosine similarity index
            self.index = faiss.IndexFlatL2(self.dimension)
            self.metadata = []
            self._save_index()
    
    def _save_index(self):
        """Save index and metadata to disk."""
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, 'w') as f:
            json.dump(self.metadata, f)
    
    def add_vector(self, task_id: str, embedding: np.ndarray):
        """Add a vector and its metadata to the index."""
        if embedding.shape[0] != self.dimension:
            raise ValueError(f"Embedding dimension {embedding.shape[0]} does not match index dimension {self.dimension}")
        
        # FAISS expects vectors as float32 and in shape (1, dimension)
        embedding_array = embedding.astype('float32').reshape(1, -1)
        
        # Add to index
        self.index.add(embedding_array)
        
        # Add metadata
        self.metadata.append(task_id)
        
        # Save to disk
        self._save_index()
    
    def update_vector(self, task_id: str, new_embedding: np.ndarray):
        """Update a vector for an existing task_id."""
        # Find the index of the task_id
        if task_id not in self.metadata:
            # If not found, just add it
            self.add_vector(task_id, new_embedding)
            return
        
        # FAISS doesn't support updates directly, so we need to rebuild
        # Get all vectors except the one to update
        indices_to_keep = [i for i, tid in enumerate(self.metadata) if tid != task_id]
        
        # Create new index
        new_index = faiss.IndexFlatL2(self.dimension)
        new_metadata = []
        
        # Add all vectors except the one being updated
        for idx in indices_to_keep:
            vector = self.index.reconstruct(idx)
            new_index.add(vector.reshape(1, -1))
            new_metadata.append(self.metadata[idx])
        
        # Add the updated vector
        new_embedding_array = new_embedding.astype('float32').reshape(1, -1)
        new_index.add(new_embedding_array)
        new_metadata.append(task_id)
        
        # Replace old index and metadata
        self.index = new_index
        self.metadata = new_metadata
        
        # Save to disk
        self._save_index()
    
    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Search for the most similar vectors.
        
        Returns:
            List of (task_id, distance) tuples, sorted by similarity (lower distance = more similar)
        """
        if self.index.ntotal == 0:
            return []
        
        # Ensure query is the right shape
        query_array = query_embedding.astype('float32').reshape(1, -1)
        
        # Search
        top_k = min(top_k, self.index.ntotal)  # Don't ask for more than we have
        distances, indices = self.index.search(query_array, top_k)
        
        # Build results
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.metadata):  # Safety check
                task_id = self.metadata[idx]
                distance = float(distances[0][i])
                results.append((task_id, distance))
        
        return results
    
    def delete_vector(self, task_id: str):
        """Delete a vector by task_id."""
        if task_id not in self.metadata:
            return
        
        # Rebuild index without the deleted vector
        indices_to_keep = [i for i, tid in enumerate(self.metadata) if tid != task_id]
        
        new_index = faiss.IndexFlatL2(self.dimension)
        new_metadata = []
        
        for idx in indices_to_keep:
            vector = self.index.reconstruct(idx)
            new_index.add(vector.reshape(1, -1))
            new_metadata.append(self.metadata[idx])
        
        self.index = new_index
        self.metadata = new_metadata
        
        self._save_index()
    
    def get_all_task_ids(self) -> List[str]:
        """Get all task_ids in the index."""
        return self.metadata.copy()
    
    def clear(self):
        """Clear all vectors from the index."""
        self.index = faiss.IndexFlatL2(self.dimension)
        self.metadata = []
        self._save_index()


class EmbeddingService:
    """Service for generating embeddings using OpenAI API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key is required for embedding generation")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = "text-embedding-3-small"  # Fast and cost-effective
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a text string."""
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            
            # Extract the embedding vector
            embedding = np.array(response.data[0].embedding, dtype=np.float32)
            return embedding
            
        except Exception as e:
            print(f"Error generating embedding: {e}")
            raise
    
    def generate_task_embedding(self, task_name: str, description: str, tags: List[str]) -> np.ndarray:
        """
        Generate embedding for a task based on its metadata.
        Combines task name, description, and tags into a single text.
        """
        # Create a comprehensive text representation
        text_parts = [task_name]
        
        if description:
            text_parts.append(description)
        
        if tags:
            text_parts.append("Tags: " + ", ".join(tags))
        
        combined_text = ". ".join(text_parts)
        
        return self.generate_embedding(combined_text)


class SemanticSearch:
    """High-level semantic search service combining VectorStore and EmbeddingService."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.vector_store = VectorStore()
        self.embedding_service = EmbeddingService(api_key)
    
    def index_task(self, task):
        """Index a LearnedTask for semantic search."""
        # Generate embedding from task metadata
        embedding = self.embedding_service.generate_task_embedding(
            task.task_name,
            task.description,
            task.tags
        )
        
        # Add to vector store
        self.vector_store.add_vector(task.task_id, embedding)
        
        # Also save embedding with the task
        task.embedding_vector = embedding
        task.save()
    
    def update_task_index(self, task):
        """Update the index for an existing task."""
        embedding = self.embedding_service.generate_task_embedding(
            task.task_name,
            task.description,
            task.tags
        )
        
        self.vector_store.update_vector(task.task_id, embedding)
        
        task.embedding_vector = embedding
        task.save()
    
    def search_tasks(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Search for tasks similar to the query.
        
        Returns:
            List of task dictionaries with similarity scores
        """
        # Generate embedding for query
        query_embedding = self.embedding_service.generate_embedding(query)
        
        # Search vector store
        results = self.vector_store.search(query_embedding, top_k)
        
        # Fetch task details from database
        from models import LearnedTask
        
        tasks_with_scores = []
        for task_id, distance in results:
            task = LearnedTask.get_by_id(task_id)
            if task:
                task_dict = task.to_dict()
                task_dict['similarity_score'] = float(1 / (1 + distance))  # Convert distance to similarity
                task_dict['distance'] = float(distance)
                tasks_with_scores.append(task_dict)
        
        return tasks_with_scores
    
    def delete_task_from_index(self, task_id: str):
        """Remove a task from the search index."""
        self.vector_store.delete_vector(task_id)
    
    def reindex_all_tasks(self):
        """Rebuild the entire search index from scratch."""
        from models import LearnedTask
        
        # Clear existing index
        self.vector_store.clear()
        
        # Get all tasks
        all_tasks = LearnedTask.get_all(limit=10000)
        
        # Index each task
        for task in all_tasks:
            try:
                self.index_task(task)
                print(f"Indexed task: {task.task_name}")
            except Exception as e:
                print(f"Failed to index task {task.task_id}: {e}")
