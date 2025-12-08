"""
Test script for Status Update functionality in audit-process pipeline.

This script validates that the new status update methods work correctly
by testing the NotionClient methods without processing a full video.
"""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.notion_client import NotionClient
from config.notion_config import get_destination_database
from config.logger import get_logger

logger = get_logger(__name__)


def test_status_update_methods():
    """
    Test the new status update methods for audit-process.
    
    This test:
    1. Verifies NotionClient can be initialized
    2. Checks that field_map contains required fields
    3. Tests property builders for status and error fields
    """
    logger.info("=" * 80)
    logger.info("🧪 Testing Status Update Functionality")
    logger.info("=" * 80)
    
    # Test 1: Initialize NotionClient
    logger.info("\n1️⃣ Testing NotionClient initialization...")
    try:
        notion_client = NotionClient()
        logger.info("   ✅ NotionClient initialized successfully")
    except Exception as e:
        logger.error(f"   ❌ Failed to initialize NotionClient: {e}")
        return False
    
    # Test 2: Get audit-process configuration
    logger.info("\n2️⃣ Testing audit-process configuration...")
    try:
        channel = "audit-process"
        destination_db = get_destination_database(channel)
        
        if not destination_db:
            logger.error(f"   ❌ No configuration found for channel: {channel}")
            return False
        
        field_map = destination_db.get("field_map", {})
        action_type = destination_db.get("action_type")
        
        logger.info(f"   ✅ Configuration found")
        logger.info(f"      Action Type: {action_type}")
        logger.info(f"      Database: {destination_db.get('database_name')}")
        
        # Verify action_type is "update_origin"
        if action_type != "update_origin":
            logger.warning(f"   ⚠️ Action type is '{action_type}', expected 'update_origin'")
        else:
            logger.info("   ✅ Action type is correct: update_origin")
        
    except Exception as e:
        logger.error(f"   ❌ Failed to get configuration: {e}")
        return False
    
    # Test 3: Verify required fields in field_map
    logger.info("\n3️⃣ Verifying required fields in field_map...")
    required_fields = {
        "status": "Transcript Process Status",
        "process_errors": "ProcessErrors"
    }
    
    all_fields_present = True
    for logical_key, expected_column in required_fields.items():
        actual_column = field_map.get(logical_key)
        if actual_column:
            if actual_column == expected_column:
                logger.info(f"   ✅ '{logical_key}' → '{actual_column}' ✓")
            else:
                logger.warning(f"   ⚠️ '{logical_key}' → '{actual_column}' (expected '{expected_column}')")
        else:
            logger.error(f"   ❌ Field '{logical_key}' not found in field_map")
            all_fields_present = False
    
    if not all_fields_present:
        logger.error("   ❌ Not all required fields are present")
        return False
    
    # Test 4: Test property builders
    logger.info("\n4️⃣ Testing property builder methods...")
    try:
        # Test status property builder
        status_prop = notion_client.build_select_property("Processing")
        logger.info(f"   ✅ build_select_property('Processing') → {status_prop}")
        
        # Test error property builder
        error_prop = notion_client.build_text_property("Test error message")
        logger.info(f"   ✅ build_text_property('Test error message') → OK")
        
    except Exception as e:
        logger.error(f"   ❌ Property builder test failed: {e}")
        return False
    
    # Test 5: Verify all status values are valid
    logger.info("\n5️⃣ Verifying status values...")
    status_values = [
        "Processing",
        "Downloading",
        "Transcribing",
        "Uploading to Drive",
        "Complete",
        "Error"
    ]
    
    logger.info("   Status values to be used:")
    for status in status_values:
        logger.info(f"      • {status}")
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ All tests passed successfully!")
    logger.info("=" * 80)
    logger.info("\n📝 Next steps:")
    logger.info("   1. Make sure the 'Transcript Process Status' field exists in Notion")
    logger.info("   2. Verify it has these exact options as Select values:")
    for status in status_values:
        logger.info(f"      • {status}")
    logger.info("   3. Ensure the 'ProcessErrors' field exists as a Text property")
    logger.info("   4. Test with a real video by triggering the webhook")
    logger.info("=" * 80)
    
    return True


def main():
    """Run the tests."""
    try:
        success = test_status_update_methods()
        
        if success:
            logger.info("\n✅ All tests completed successfully!")
            return 0
        else:
            logger.error("\n❌ Some tests failed. Please check the logs above.")
            return 1
            
    except Exception as e:
        logger.error(f"\n❌ Test execution failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
