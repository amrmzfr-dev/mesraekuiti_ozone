# Hardcoded Access Control Configuration
# Modify these lists to control who has access to your system

# ADMIN USERS - Full access to everything
HARDCODED_ADMINS = [
    'admin',      # Default admin user
    'yoga',       # Your username
    'manager',    # Manager access
    # Add more admin usernames here
]

# REGULAR USERS - Limited access
HARDCODED_USERS = [
    'user1',      # Regular user 1
    'user2',      # Regular user 2
    'operator',   # Operator access
    # Add more regular usernames here
]

# ACCESS LEVEL DEFINITIONS
ACCESS_LEVELS = {
    'admin': {
        'access_level': 'admin',
        'can_manage_devices': True,
        'can_view_stats': True,
        'can_export_data': True,
        'can_delete_data': True,
        'can_modify_settings': True,
    },
    'user': {
        'access_level': 'user',
        'can_manage_devices': False,
        'can_view_stats': True,
        'can_export_data': False,
        'can_delete_data': False,
        'can_modify_settings': False,
    }
}

def get_user_access(username):
    """
    Get access permissions for a user based on hardcoded lists
    
    Args:
        username (str): The username to check
        
    Returns:
        dict: Access permissions or None if user not authorized
    """
    if username in HARDCODED_ADMINS:
        return ACCESS_LEVELS['admin']
    elif username in HARDCODED_USERS:
        return ACCESS_LEVELS['user']
    else:
        return None

def is_user_authorized(username):
    """
    Check if a user is authorized to access the system
    
    Args:
        username (str): The username to check
        
    Returns:
        bool: True if authorized, False otherwise
    """
    return username in HARDCODED_ADMINS or username in HARDCODED_USERS

def get_authorized_users():
    """
    Get list of all authorized users
    
    Returns:
        dict: Dictionary with admin and user lists
    """
    return {
        'admins': HARDCODED_ADMINS.copy(),
        'users': HARDCODED_USERS.copy(),
        'total_count': len(HARDCODED_ADMINS) + len(HARDCODED_USERS)
    }
