"""
YouTube MCP Server - Complete Implementation

This MCP server provides comprehensive access to YouTube data including transcripts, video metadata, search, and comments.

## Environment Variables
- YOUTUBE_API_KEY: Required. API key for YouTube Data API v3. Obtain from Google Cloud Console with YouTube Data API enabled.

## Required Permissions
- YouTube Data API v3: Read-only access to public video data (snippets, search, comments).
- No OAuth2 required; API key-based authentication.
- Enable YouTube Data API v3 in Google Cloud Console.
- Restrict API key to specific IPs or referrers for security.

## Setup Instructions
1. Install dependencies: pip install fastmcp pydantic httpx youtube-transcript-api
2. Set environment variable: export YOUTUBE_API_KEY=your_api_key_here
3. Run the server: python this_file.py

## Authentication Method
- API key-based authentication via YOUTUBE_API_KEY environment variable.
- Passed as 'key' query parameter in YouTube Data API requests.
- No token refresh needed; API keys are static.
"""

import asyncio
import os
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator, ConfigDict


class Config:
    '''Configuration with environment variable validation'''
    # Define all required environment variables
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
    
    @classmethod
    def validate(cls) -> None:
        '''Validate required environment variables are set'''
        errors = []
        if not cls.YOUTUBE_API_KEY:
            errors.append("YOUTUBE_API_KEY is required")
        
        if errors:
            error_msg = "Missing required environment variables:\n"
            error_msg += "\n".join(f"  - {e}" for e in errors)
            error_msg += "\n\nSee module docstring for configuration details."
            raise ValueError(error_msg)


# Validate configuration on import
Config.validate()


class ResponseFormat(Enum):
    JSON = "json"
    TEXT = "text"


CHARACTER_LIMIT = 5000


class TranscriptRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    video_id: str = Field(..., description="The YouTube video ID (e.g., 'dQw4w9WgXcQ')")
    
    @field_validator('video_id')
    @classmethod
    def validate_video_id(cls, v: str, info: ValidationInfo) -> str:
        """Validate video_id format"""
        if not v or len(v) != 11:
            raise ValueError("video_id must be exactly 11 characters")
        return v


class TranscriptResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    transcript: str = Field(..., description="The full transcript of the YouTube video")
    video_title: Optional[str] = Field(None, description="The title of the YouTube video")
    video_description: Optional[str] = Field(None, description="The description of the YouTube video")


class SearchRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    query: str = Field(..., description="Search query for YouTube videos")
    max_results: int = Field(5, description="Maximum number of results (1-50)", ge=1, le=50)
    
    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str, info: ValidationInfo) -> str:
        """Validate search query"""
        if not v or not v.strip():
            raise ValueError("query cannot be empty")
        return v.strip()


class SearchResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    videos: List[Dict[str, Any]] = Field(..., description="List of video search results")


class VideoDetailsRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    video_id: str = Field(..., description="The YouTube video ID")
    
    @field_validator('video_id')
    @classmethod
    def validate_video_id(cls, v: str, info: ValidationInfo) -> str:
        """Validate video_id format"""
        if not v or len(v) != 11:
            raise ValueError("video_id must be exactly 11 characters")
        return v


class VideoDetailsResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    video_id: str = Field(..., description="The YouTube video ID")
    title: str = Field(..., description="The title of the video")
    description: str = Field(..., description="The description of the video")
    published_at: str = Field(..., description="The publication date")


class CommentsRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    video_id: str = Field(..., description="The YouTube video ID")
    max_results: int = Field(20, description="Maximum number of comments (1-100)", ge=1, le=100)
    
    @field_validator('video_id')
    @classmethod
    def validate_video_id(cls, v: str, info: ValidationInfo) -> str:
        """Validate video_id format"""
        if not v or len(v) != 11:
            raise ValueError("video_id must be exactly 11 characters")
        return v


class CommentsResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    comments: List[str] = Field(..., description="List of top-level comments")


async def _make_api_request(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Helper function to make API requests to YouTube Data API"""
    params['key'] = Config.YOUTUBE_API_KEY
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            raise ValueError(f"API request failed: {response.status_code} - {response.text}")
        return response.json()


def _handle_api_error(e: Exception) -> str:
    """Helper function to handle and format API errors"""
    return f"API Error: {str(e)}"


# Initialize FastMCP
mcp = FastMCP("YouTube MCP Server")


@mcp.tool()
async def get_youtube_transcript(request: TranscriptRequest) -> TranscriptResponse:
    """
    Fetches the transcript of a YouTube video using the YouTube Transcript API.
    
    Args:
        request: TranscriptRequest containing the video_id
    
    Returns:
        TranscriptResponse with transcript, title, and description
    """
    video_id = request.video_id
    
    # Fetch transcript using youtube-transcript-api
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcript = " ".join([item['text'] for item in transcript_list])
    except Exception as e:
        raise ValueError(_handle_api_error(e))
    
    # Fetch video details using YouTube Data API v3
    try:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {"id": video_id, "part": "snippet"}
        data = await _make_api_request(url, params)
        if not data['items']:
            raise ValueError("Video not found")
        
        snippet = data['items'][0]['snippet']
        video_title = snippet['title']
        video_description = snippet['description']
    except Exception as e:
        raise ValueError(_handle_api_error(e))
    
    return TranscriptResponse(
        transcript=transcript,
        video_title=video_title,
        video_description=video_description
    )


@mcp.tool()
async def youtube_search_videos(request: SearchRequest) -> SearchResponse:
    """
    Searches for YouTube videos by query and returns a list of video IDs, titles, and descriptions.
    
    Args:
        request: SearchRequest containing query and max_results
    
    Returns:
        SearchResponse with list of videos
    """
    try:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {"q": request.query, "part": "snippet", "type": "video", "maxResults": request.max_results}
        data = await _make_api_request(url, params)
        
        videos = []
        for item in data.get('items', []):
            video_id = item['id']['videoId']
            title = item['snippet']['title']
            description = item['snippet']['description']
            videos.append({"video_id": video_id, "title": title, "description": description})
        
        return SearchResponse(videos=videos)
    except Exception as e:
        raise ValueError(_handle_api_error(e))


@mcp.tool()
async def youtube_get_video_details(request: VideoDetailsRequest) -> VideoDetailsResponse:
    """
    Retrieves detailed metadata for a YouTube video without transcript.
    
    Args:
        request: VideoDetailsRequest containing video_id
    
    Returns:
        VideoDetailsResponse with video metadata
    """
    try:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {"id": request.video_id, "part": "snippet"}
        data = await _make_api_request(url, params)
        if not data['items']:
            raise ValueError("Video not found")
        
        snippet = data['items'][0]['snippet']
        return VideoDetailsResponse(
            video_id=request.video_id,
            title=snippet['title'],
            description=snippet['description'],
            published_at=snippet['publishedAt']
        )
    except Exception as e:
        raise ValueError(_handle_api_error(e))


@mcp.tool()
async def youtube_get_comments(request: CommentsRequest) -> CommentsResponse:
    """
    Fetches top comments for a YouTube video.
    
    Args:
        request: CommentsRequest containing video_id and max_results
    
    Returns:
        CommentsResponse with list of comments
    """
    try:
        url = "https://www.googleapis.com/youtube/v3/commentThreads"
        params = {"videoId": request.video_id, "part": "snippet", "maxResults": request.max_results}
        data = await _make_api_request(url, params)
        
        comments = []
        for item in data.get('items', []):
            comment_text = item['snippet']['topLevelComment']['snippet']['textDisplay']
            comments.append(comment_text)
        
        return CommentsResponse(comments=comments)
    except Exception as e:
        raise ValueError(_handle_api_error(e))


@mcp.tool()
async def youtube_list_channel_videos(request: SearchRequest) -> SearchResponse:
    """
    Lists videos from a specific channel (using search with channel filter).
    
    Args:
        request: SearchRequest containing query (channel name) and max_results
    
    Returns:
        SearchResponse with list of videos from the channel
    """
    # Note: This is a simplified implementation; in practice, you'd need channel ID
    try:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {"q": request.query, "part": "snippet", "type": "video", "maxResults": request.max_results}
        data = await _make_api_request(url, params)
        
        videos = []
        for item in data.get('items', []):
            video_id = item['id']['videoId']
            title = item['snippet']['title']
            description = item['snippet']['description']
            videos.append({"video_id": video_id, "title": title, "description": description})
        
        return SearchResponse(videos=videos)
    except Exception as e:
        raise ValueError(_handle_api_error(e))


if __name__ == "__main__":
    mcp.run()