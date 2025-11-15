#!/usr/bin/env python3
"""
Test script for error handling in download methods.
This script tests the retry logic and error handling without requiring Blender.
"""

import sys
import time
import unittest
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import Timeout, ConnectionError, HTTPError


# Mock bpy module since we're testing without Blender
sys.modules['bpy'] = MagicMock()

# Now we can import the generator
from generator import CityGenerator


class TestErrorHandling(unittest.TestCase):
    """Test error handling in CityGenerator"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Patch bpy operations to avoid Blender dependency
        with patch('generator.bpy'):
            self.generator = CityGenerator(
                min_lat=48.8566,
                max_lat=48.8666,
                min_lon=2.3522,
                max_lon=2.3622
            )
        # Reduce retries for faster testing
        self.generator.max_retries = 2
        self.generator.backoff_factor = 1
    
    def test_retry_on_timeout(self):
        """Test that requests are retried on timeout"""
        mock_func = Mock()
        mock_func.side_effect = [
            Timeout("Connection timed out"),
            Mock(status_code=200, json=lambda: {"test": "data"})
        ]
        
        response = self.generator._retry_request(
            mock_func,
            "Test operation",
            "http://test.url"
        )
        
        # Should have been called twice (1 failure, 1 success)
        self.assertEqual(mock_func.call_count, 2)
        self.assertIsNotNone(response)
        self.assertEqual(len(self.generator.errors), 0)
    
    def test_retry_on_connection_error(self):
        """Test that requests are retried on connection error"""
        mock_func = Mock()
        mock_func.side_effect = [
            ConnectionError("Connection refused"),
            Mock(status_code=200, json=lambda: {"test": "data"})
        ]
        
        response = self.generator._retry_request(
            mock_func,
            "Test operation",
            "http://test.url"
        )
        
        # Should have been called twice
        self.assertEqual(mock_func.call_count, 2)
        self.assertIsNotNone(response)
    
    def test_max_retries_exceeded(self):
        """Test that after max retries, None is returned"""
        mock_func = Mock()
        mock_func.side_effect = Timeout("Connection timed out")
        
        response = self.generator._retry_request(
            mock_func,
            "Test operation",
            "http://test.url"
        )
        
        # Should have been called max_retries times
        self.assertEqual(mock_func.call_count, self.generator.max_retries)
        self.assertIsNone(response)
        # Should have an error logged
        self.assertGreater(len(self.generator.errors), 0)
    
    def test_no_retry_on_client_error(self):
        """Test that 4xx errors (except 429) are not retried"""
        mock_func = Mock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_func.return_value = mock_response
        
        response = self.generator._retry_request(
            mock_func,
            "Test operation",
            "http://test.url"
        )
        
        # Should only be called once (no retry on 404)
        self.assertEqual(mock_func.call_count, 1)
        self.assertIsNone(response)
        self.assertGreater(len(self.generator.errors), 0)
    
    def test_retry_on_server_error(self):
        """Test that 5xx errors are retried"""
        mock_func = Mock()
        mock_response_error = Mock()
        mock_response_error.status_code = 503
        mock_response_error.raise_for_status.side_effect = HTTPError(response=mock_response_error)
        
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status.return_value = None
        
        mock_func.side_effect = [
            mock_response_error,
            mock_response_success
        ]
        
        response = self.generator._retry_request(
            mock_func,
            "Test operation",
            "http://test.url"
        )
        
        # Should have been called twice
        self.assertEqual(mock_func.call_count, 2)
        self.assertIsNotNone(response)
    
    def test_rate_limit_429_handling(self):
        """Test that 429 rate limit errors are properly handled with longer waits"""
        mock_func = Mock()
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.raise_for_status.side_effect = HTTPError(response=mock_response_429)
        
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status.return_value = None
        
        # First call: 429, second call: success
        mock_func.side_effect = [
            mock_response_429,
            mock_response_success
        ]
        
        with patch('time.sleep'):  # Don't actually sleep during tests
            response = self.generator._retry_request(
                mock_func,
                "Test operation",
                "http://test.url"
            )
        
        # Should have succeeded on second attempt
        self.assertIsNotNone(response)
        self.assertEqual(mock_func.call_count, 2)
    
    def test_rate_limit_429_max_retries(self):
        """Test that 429 errors eventually fail after max retries"""
        mock_func = Mock()
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.raise_for_status.side_effect = HTTPError(response=mock_response_429)
        
        mock_func.return_value = mock_response_429
        
        with patch('time.sleep'):  # Don't actually sleep during tests
            response = self.generator._retry_request(
                mock_func,
                "Test operation",
                "http://test.url"
            )
        
        # Should fail after all retries
        self.assertIsNone(response)
        self.assertEqual(mock_func.call_count, self.generator.max_retries)
        # Should have an error about rate limiting
        self.assertTrue(any('Rate limit' in error or '429' in error for error in self.generator.errors))
    
    def test_osm_data_download_with_failure(self):
        """Test OSM data download with simulated failure"""
        with patch('generator.requests.post') as mock_post:
            mock_post.side_effect = Timeout("Connection timed out")
            
            result = self.generator.download_osm_data()
            
            # Should return empty elements
            self.assertEqual(result, {'elements': []})
            # Should have errors or warnings logged
            self.assertTrue(len(self.generator.errors) > 0 or len(self.generator.warnings) > 0)
    
    def test_osm_data_download_with_empty_response(self):
        """Test OSM data download with empty but valid response"""
        with patch('generator.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {'elements': []}
            mock_post.return_value = mock_response
            
            result = self.generator.download_osm_data()
            
            # Should return empty elements
            self.assertEqual(result, {'elements': []})
            # Should have a warning about empty results
            self.assertGreater(len(self.generator.warnings), 0)
    
    def test_osm_data_download_with_invalid_json(self):
        """Test OSM data download with invalid JSON response"""
        with patch('generator.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status.return_value = None
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_post.return_value = mock_response
            
            result = self.generator.download_osm_data()
            
            # Should return empty elements
            self.assertEqual(result, {'elements': []})
            # Should have warnings logged (will try all servers)
            self.assertGreater(len(self.generator.warnings), 0)
    
    def test_osm_data_download_with_server_fallback(self):
        """Test that OSM download falls back to alternative servers"""
        with patch('generator.requests.post') as mock_post:
            # First server fails with timeout, second succeeds
            mock_response_success = Mock()
            mock_response_success.status_code = 200
            mock_response_success.raise_for_status.return_value = None
            mock_response_success.json.return_value = {'elements': [{'type': 'node', 'id': 1}]}
            
            # Simulate: first server times out on all attempts, second server succeeds
            call_count = 0
            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                # First 2 calls are retries on server 1 (fail)
                if call_count <= 2:
                    raise Timeout("Connection timed out")
                # Third call is server 2 (success)
                return mock_response_success
            
            mock_post.side_effect = side_effect
            
            result = self.generator.download_osm_data()
            
            # Should successfully return data from second server
            self.assertEqual(len(result.get('elements', [])), 1)
            # Should have been called at least 3 times (2 fails + 1 success)
            self.assertGreaterEqual(call_count, 3)
    
    def test_osm_data_download_all_servers_fail(self):
        """Test that OSM download tries all servers before giving up"""
        with patch('generator.requests.post') as mock_post:
            mock_post.side_effect = Timeout("Connection timed out")
            
            result = self.generator.download_osm_data()
            
            # Should return empty elements
            self.assertEqual(result, {'elements': []})
            # Should have warnings about all servers failing
            self.assertGreater(len(self.generator.warnings), 0)
            # Check that multiple servers were attempted
            warning = self.generator.warnings[0]
            self.assertIn('all', warning.lower())
    
    def test_gateway_timeout_handling(self):
        """Test that 504 Gateway Timeout errors get special handling"""
        mock_func = Mock()
        mock_response_error = Mock()
        mock_response_error.status_code = 504
        mock_response_error.raise_for_status.side_effect = HTTPError(response=mock_response_error)
        
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status.return_value = None
        
        # First call: 504, second call: success
        mock_func.side_effect = [
            mock_response_error,
            mock_response_success
        ]
        
        with patch('time.sleep'):  # Don't actually sleep during tests
            response = self.generator._retry_request(
                mock_func,
                "Test operation",
                "http://test.url"
            )
        
        # Should have succeeded on second attempt
        self.assertIsNotNone(response)
        self.assertEqual(mock_func.call_count, 2)
    
    def test_error_and_warning_tracking(self):
        """Test that errors and warnings are properly tracked"""
        # Start with no errors/warnings
        self.assertEqual(len(self.generator.errors), 0)
        self.assertEqual(len(self.generator.warnings), 0)
        
        # Simulate a download with failures
        with patch('generator.requests.post') as mock_post:
            mock_post.side_effect = Timeout("Connection timed out")
            self.generator.download_osm_data()
        
        # Should have errors or warnings
        self.assertTrue(len(self.generator.errors) > 0 or len(self.generator.warnings) > 0)


class TestConfigurableParameters(unittest.TestCase):
    """Test configurable retry parameters"""
    
    def test_default_parameters(self):
        """Test default retry parameters"""
        with patch('generator.bpy'):
            generator = CityGenerator(48.8, 48.9, 2.3, 2.4)
        
        self.assertEqual(generator.max_retries, 3)
        self.assertEqual(generator.initial_timeout, 30)
        self.assertEqual(generator.backoff_factor, 2)
    
    def test_exponential_backoff(self):
        """Test that timeout increases with exponential backoff"""
        with patch('generator.bpy'):
            generator = CityGenerator(48.8, 48.9, 2.3, 2.4)
        
        mock_func = Mock()
        mock_func.side_effect = Timeout("Connection timed out")
        
        with patch('time.sleep'):  # Don't actually sleep during tests
            generator._retry_request(mock_func, "Test", "url")
        
        # Check that timeout parameter increases
        calls = mock_func.call_args_list
        # First call should have timeout = 30
        self.assertEqual(calls[0][1]['timeout'], 30)
        # Second call should have timeout = 60 (30 * 2^1)
        self.assertEqual(calls[1][1]['timeout'], 60)
        # Third call should have timeout = 120 (30 * 2^2)
        self.assertEqual(calls[2][1]['timeout'], 120)


class TestMultithreading(unittest.TestCase):
    """Test multithreading functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        with patch('generator.bpy'):
            self.generator = CityGenerator(
                min_lat=48.8566,
                max_lat=48.8568,  # Very small area for faster testing
                min_lon=2.3522,
                max_lon=2.3524
            )
        # Reduce workers for faster testing
        self.generator.max_workers = 2
        self.generator.max_retries = 1
        self.generator.requests_per_second = 100  # Fast rate for testing
    
    def test_multithreading_configuration(self):
        """Test that multithreading is properly configured"""
        self.assertEqual(self.generator.max_workers, 2)
        self.assertIsNotNone(self.generator._progress_lock)
        self.assertEqual(type(self.generator._progress_lock).__name__, 'lock')
        # Test rate limiting configuration
        self.assertIsNotNone(self.generator._rate_limit_lock)
        self.assertEqual(self.generator.requests_per_second, 100)
    
    def test_fetch_elevation_point_success(self):
        """Test fetching a single elevation point successfully"""
        with patch('generator.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                'results': [{'elevation': 42.5}]
            }
            mock_get.return_value = mock_response
            
            i, j, elevation, success = self.generator._fetch_elevation_point(48.8566, 2.3522, 0, 0)
            
            self.assertEqual(i, 0)
            self.assertEqual(j, 0)
            self.assertEqual(elevation, 42.5)
            self.assertTrue(success)
    
    def test_fetch_elevation_point_failure(self):
        """Test fetching a single elevation point with failure"""
        with patch('generator.requests.get') as mock_get:
            mock_get.side_effect = Timeout("Connection timed out")
            
            i, j, elevation, success = self.generator._fetch_elevation_point(48.8566, 2.3522, 1, 2)
            
            self.assertEqual(i, 1)
            self.assertEqual(j, 2)
            self.assertEqual(elevation, 0)
            self.assertFalse(success)
    
    def test_download_terrain_data_with_multithreading(self):
        """Test terrain data download uses multithreading"""
        with patch('generator.requests.get') as mock_get:
            # Create a mock response that returns different elevations
            def mock_response(*args, **kwargs):
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                # Return varying elevation based on the URL
                lat = float(args[0].split('=')[1].split(',')[0])
                response.json.return_value = {
                    'results': [{'elevation': lat * 10}]  # Simple calculation
                }
                return response
            
            mock_get.side_effect = mock_response
            
            result = self.generator.download_terrain_data()
            
            # Check that result is a numpy array
            self.assertIsNotNone(result)
            self.assertEqual(len(result.shape), 2)
            
            # Check that some elevation data was retrieved
            # (we can't check exact values due to threading, but should be non-zero)
            self.assertTrue(result.max() > 0)
            
            # Check that requests.get was called multiple times (parallel execution)
            # For a very small area, we should have at least a 20x20 grid (400 points)
            self.assertGreater(mock_get.call_count, 100)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
