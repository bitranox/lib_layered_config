"""Tests for identifier validation and Layer enum."""

from __future__ import annotations

import pytest

from lib_layered_config.domain.identifiers import (
    DEFAULT_MAX_PROFILE_LENGTH,
    Layer,
    is_valid_profile_name,
    validate_hostname,
    validate_identifier,
    validate_path_segment,
    validate_profile,
    validate_profile_name,
    validate_vendor_app,
)

# Import internal constant for testing
from lib_layered_config.domain.identifiers import ABSOLUTE_MAX_PROFILE_LENGTH


class TestValidatePathSegment:
    """Tests for validate_path_segment - the core validation function.

    This is the central sanitization function that ensures all identifiers
    (vendor, app, slug, profile, hostname) are safe for filesystem paths
    on both Windows and Linux.
    """

    # ========== VALID INPUTS ==========

    @pytest.mark.parametrize(
        "value",
        [
            "myapp",
            "a",  # Single character
            "x1",  # Single char + number
            "app123",
            "123app",  # Can start with number
            "MyApp",  # Mixed case
            "MYAPP",  # All uppercase
            "my-app",  # Hyphen
            "my_app",  # Underscore
            "my.app",  # Dot in middle
            "my-app-v2",  # Multiple hyphens
            "my_app_v2",  # Multiple underscores
            "app.v1.2",  # Multiple dots
            "a-b_c.d",  # Mixed separators
            "A1-B2_C3.D4",  # Complex valid name
        ],
    )
    def test_accepts_valid_identifiers(self, value: str) -> None:
        """Valid identifiers should pass through unchanged."""
        assert validate_path_segment(value, "test") == value

    # ========== EMPTY / WHITESPACE ==========

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="test cannot be empty"):
            validate_path_segment("", "test")

    @pytest.mark.parametrize(
        "value",
        [
            " ",  # Single space
            "  ",  # Multiple spaces
            "\t",  # Tab
            "\n",  # Newline
            " app",  # Leading space
            "app ",  # Trailing space
            "my app",  # Space in middle
        ],
    )
    def test_rejects_whitespace(self, value: str) -> None:
        """Whitespace in any position should be rejected."""
        with pytest.raises(ValueError, match="test contains invalid characters"):
            validate_path_segment(value, "test")

    # ========== NON-ASCII / UNICODE ==========

    @pytest.mark.parametrize(
        "value",
        [
            "café",  # Accented character
            "naïve",  # Diaeresis
            "über",  # Umlaut
            "日本語",  # Japanese
            "中文",  # Chinese
            "한글",  # Korean
            "العربية",  # Arabic
            "app🚀",  # Emoji
            "test™",  # Trademark symbol
            "app©2024",  # Copyright symbol
            "µapp",  # Micro sign
            "app°",  # Degree symbol
            "app\u2014name",  # Em dash (not hyphen)
            "app\u2013name",  # En dash (not hyphen)
            "app\u2019name",  # Smart quote / right single quotation mark
            "\u201cquoted\u201d",  # Smart double quotes (Unicode)
        ],
    )
    def test_rejects_non_ascii_characters(self, value: str) -> None:
        """Non-ASCII characters should be rejected for cross-platform safety."""
        with pytest.raises(ValueError, match="test contains non-ASCII characters"):
            validate_path_segment(value, "test")

    # ========== PATH TRAVERSAL ATTACKS ==========

    @pytest.mark.parametrize(
        "value",
        [
            "../etc",  # Unix relative path up
            "..\\windows",  # Windows relative path up
            "/etc/passwd",  # Unix absolute path
            "\\windows\\system32",  # Windows absolute path
            "C:\\Windows",  # Windows drive path
            "foo/bar",  # Forward slash
            "foo\\bar",  # Backslash
        ],
    )
    def test_rejects_path_traversal_attempts(self, value: str) -> None:
        """Path traversal patterns should be rejected."""
        with pytest.raises(ValueError, match="test contains invalid characters"):
            validate_path_segment(value, "test")

    def test_rejects_ellipsis(self) -> None:
        """Multiple dots starting a value should be rejected (starts with dot)."""
        with pytest.raises(ValueError, match="test cannot start with a dot"):
            validate_path_segment("...", "test")

    # ========== WINDOWS-INVALID CHARACTERS ==========

    @pytest.mark.parametrize(
        "char,desc",
        [
            ("<", "less than"),
            (">", "greater than"),
            (":", "colon"),
            ('"', "double quote"),
            ("|", "pipe"),
            ("?", "question mark"),
            ("*", "asterisk"),
            ("/", "forward slash"),
            ("\\", "backslash"),
        ],
    )
    def test_rejects_windows_invalid_characters(self, char: str, desc: str) -> None:
        """Characters invalid on Windows should be rejected."""
        with pytest.raises(ValueError, match="test contains invalid characters"):
            validate_path_segment(f"app{char}name", "test")

    def test_rejects_null_byte(self) -> None:
        """Null byte injection should be rejected."""
        with pytest.raises(ValueError, match="test contains invalid characters"):
            validate_path_segment("app\x00name", "test")

    # ========== PREFIX RESTRICTIONS ==========

    @pytest.mark.parametrize(
        "value,expected_error",
        [
            (".hidden", "cannot start with a dot"),
            ("..hidden", "cannot start with a dot"),
            ("..", "cannot start with a dot"),
            ("-app", "must start with an alphanumeric"),
            ("_app", "must start with an alphanumeric"),
        ],
    )
    def test_rejects_invalid_prefix(self, value: str, expected_error: str) -> None:
        """Values starting with dot, hyphen, or underscore should be rejected."""
        with pytest.raises(ValueError, match=expected_error):
            validate_path_segment(value, "test")

    # ========== SUFFIX RESTRICTIONS ==========

    @pytest.mark.parametrize(
        "value",
        [
            "app.",  # Trailing dot
            "app..",  # Multiple trailing dots
        ],
    )
    def test_rejects_trailing_dot(self, value: str) -> None:
        """Trailing dots (Windows restriction) should be rejected."""
        with pytest.raises(ValueError, match="test cannot end with a dot or space"):
            validate_path_segment(value, "test")

    # ========== WINDOWS RESERVED NAMES ==========

    @pytest.mark.parametrize(
        "name",
        [
            # Device names
            "CON",
            "PRN",
            "AUX",
            "NUL",
            # COM ports
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            # LPT ports
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        ],
    )
    def test_rejects_windows_reserved_names(self, name: str) -> None:
        """Windows reserved device names should be rejected (case-insensitive)."""
        with pytest.raises(ValueError, match="test is a Windows reserved name"):
            validate_path_segment(name, "test")
        # Also test lowercase
        with pytest.raises(ValueError, match="test is a Windows reserved name"):
            validate_path_segment(name.lower(), "test")

    @pytest.mark.parametrize(
        "name",
        [
            "CON.txt",  # Reserved name with extension
            "con.cfg",
            "PRN.log",
            "NUL.toml",
            "COM1.json",
            "LPT1.yaml",
        ],
    )
    def test_rejects_windows_reserved_names_with_extension(self, name: str) -> None:
        """Windows reserved names with extensions should also be rejected."""
        with pytest.raises(ValueError, match="test is a Windows reserved name"):
            validate_path_segment(name, "test")

    @pytest.mark.parametrize(
        "name",
        [
            "CONSOLE",  # Contains CON but not reserved
            "PRINTER",  # Contains PRN but not reserved
            "AUXILIARY",  # Contains AUX but not reserved
            "NULL",  # Contains NUL but not reserved
            "COM10",  # COM10 is not reserved
            "LPT10",  # LPT10 is not reserved
            "ACOM1",  # Not starting with reserved name
            "CONMAN",  # CON at start but longer
        ],
    )
    def test_accepts_names_similar_to_reserved(self, name: str) -> None:
        """Names similar to but not matching reserved names should be accepted."""
        assert validate_path_segment(name, "test") == name

    # ========== ERROR MESSAGE FORMATTING ==========

    @pytest.mark.parametrize(
        "param_name",
        ["vendor", "app", "slug", "profile", "hostname", "custom_param"],
    )
    def test_error_message_includes_param_name(self, param_name: str) -> None:
        """Error messages should include the parameter name for clarity."""
        with pytest.raises(ValueError, match=param_name):
            validate_path_segment("", param_name)


class TestValidateIdentifier:
    """Tests for validate_identifier function.

    This function validates vendor, app, slug, and profile parameters
    that become directory names in configuration paths.
    """

    # ========== VALID IDENTIFIERS ==========

    @pytest.mark.parametrize(
        "value",
        [
            "myapp",
            "my-app",
            "my_app",
            "my.app",
            "app123",
            "123app",
            "MyApp",
            "MYAPP",
            "Acme",
            "AcmeCorp",
            "acme-corp",
            "v1",
            "v1.2.3",
            "config-kit",
            "db-manager",
        ],
    )
    def test_accepts_valid_identifiers(self, value: str) -> None:
        """Valid identifiers should pass through unchanged."""
        assert validate_identifier(value, "slug") == value

    # ========== INVALID IDENTIFIERS ==========

    @pytest.mark.parametrize(
        "value,error_pattern",
        [
            ("", "slug cannot be empty"),
            ("../etc", "slug contains invalid characters"),
            ("..\\windows", "slug contains invalid characters"),
            ("/bad", "slug contains invalid characters"),
            (".hidden", "slug cannot start with a dot"),
            ("-app", "slug must start with an alphanumeric"),
            ("_app", "slug must start with an alphanumeric"),
            ("app.", "slug cannot end with a dot"),
            ("café", "slug contains non-ASCII"),
            ("app🚀", "slug contains non-ASCII"),
            ("CON", "slug is a Windows reserved name"),
            ("prn", "slug is a Windows reserved name"),
            ("my app", "slug contains invalid characters"),
            ("app<>", "slug contains invalid characters"),
            ('app"name', "slug contains invalid characters"),
        ],
    )
    def test_rejects_invalid_identifiers(self, value: str, error_pattern: str) -> None:
        """Invalid identifiers should raise ValueError with descriptive message."""
        with pytest.raises(ValueError, match=error_pattern):
            validate_identifier(value, "slug")

    # ========== PARAMETER NAME IN ERROR ==========

    @pytest.mark.parametrize("param_name", ["slug", "profile"])
    def test_error_includes_param_name(self, param_name: str) -> None:
        """Error message should include the parameter name."""
        with pytest.raises(ValueError, match=param_name):
            validate_identifier("", param_name)


class TestValidateVendorApp:
    """Tests for validate_vendor_app function.

    This function validates vendor and app parameters which allow spaces
    (for macOS/Windows paths like /Library/Application Support/Acme Corp/My App/).
    """

    # ========== VALID VENDOR/APP NAMES ==========

    @pytest.mark.parametrize(
        "value",
        [
            "Acme",
            "Acme Corp",  # Space allowed
            "My App",  # Space allowed
            "Btx Fix Mcp",  # Multiple spaces
            "DatabaseManager",
            "DB-Manager",
            "My_App",
            "App v2.0",  # Space and dot
            "Company Name Inc",
            "123App",  # Start with number
        ],
    )
    def test_accepts_valid_vendor_app(self, value: str) -> None:
        """Valid vendor/app names (including spaces) should pass."""
        assert validate_vendor_app(value, "vendor") == value
        assert validate_vendor_app(value, "app") == value

    # ========== INVALID VENDOR/APP NAMES ==========

    @pytest.mark.parametrize(
        "value,error_pattern",
        [
            ("", "vendor cannot be empty"),
            ("../etc", "vendor contains invalid characters"),
            ("..\\windows", "vendor contains invalid characters"),
            ("/bad", "vendor contains invalid characters"),
            (".hidden", "vendor cannot start with a dot"),
            ("-app", "vendor must start with an alphanumeric"),
            ("_app", "vendor must start with an alphanumeric"),
            (" App", "vendor must start with an alphanumeric"),  # Leading space
            ("App ", "vendor cannot end with a dot or space"),  # Trailing space
            ("App.", "vendor cannot end with a dot or space"),  # Trailing dot
            ("café", "vendor contains non-ASCII"),
            ("App🚀", "vendor contains non-ASCII"),
            ("CON", "vendor is a Windows reserved name"),
            ("prn", "vendor is a Windows reserved name"),
            ("app<test>", "vendor contains invalid characters"),
            ('app"name', "vendor contains invalid characters"),
            ("app|name", "vendor contains invalid characters"),
        ],
    )
    def test_rejects_invalid_vendor_app(self, value: str, error_pattern: str) -> None:
        """Invalid vendor/app names should raise ValueError."""
        with pytest.raises(ValueError, match=error_pattern):
            validate_vendor_app(value, "vendor")

    # ========== PARAMETER NAME IN ERROR ==========

    @pytest.mark.parametrize("param_name", ["vendor", "app"])
    def test_error_includes_param_name(self, param_name: str) -> None:
        """Error message should include the parameter name."""
        with pytest.raises(ValueError, match=param_name):
            validate_vendor_app("", param_name)


class TestValidateHostname:
    """Tests for validate_hostname function.

    Hostnames are used in paths like ``hosts/{hostname}.toml``.
    They have slightly different rules than identifiers (allow FQDNs).
    """

    # ========== VALID HOSTNAMES ==========

    @pytest.mark.parametrize(
        "value",
        [
            "localhost",
            "webserver",
            "web-server-01",
            "server01",
            "WEBSERVER",
            "WebServer",
            # FQDNs
            "server.local",
            "server.example.com",
            "web-01.prod.example.com",
            "ns1.subdomain.domain.tld",
            # IP-like (numeric hostnames are valid)
            "192",
            "server192",
        ],
    )
    def test_accepts_valid_hostnames(self, value: str) -> None:
        """Valid hostnames should pass through unchanged."""
        assert validate_hostname(value) == value

    # ========== INVALID HOSTNAMES ==========

    @pytest.mark.parametrize(
        "value,error_pattern",
        [
            ("", "hostname cannot be empty"),
            ("../etc", "hostname contains invalid characters"),
            ("..\\windows", "hostname contains invalid characters"),
            ("/etc/passwd", "hostname contains invalid characters"),
            (".local", "hostname must start with an alphanumeric"),
            ("-server", "hostname must start with an alphanumeric"),
            ("sërvér", "hostname contains non-ASCII"),
            ("服务器", "hostname contains non-ASCII"),
            ("server🖥️", "hostname contains non-ASCII"),
            ("CON", "hostname is a Windows reserved name"),
            ("prn", "hostname is a Windows reserved name"),
            ("NUL.local", "hostname is a Windows reserved name"),
            ("server<name>", "hostname contains invalid characters"),
            ("server|name", "hostname contains invalid characters"),
            ("server:8080", "hostname contains invalid characters"),
        ],
    )
    def test_rejects_invalid_hostnames(self, value: str, error_pattern: str) -> None:
        """Invalid hostnames should raise ValueError with descriptive message."""
        with pytest.raises(ValueError, match=error_pattern):
            validate_hostname(value)


class TestLayerEnum:
    """Tests for Layer enumeration."""

    def test_layer_values_are_strings(self) -> None:
        assert Layer.APP == "app"
        assert Layer.HOST == "host"
        assert Layer.USER == "user"
        assert Layer.DOTENV == "dotenv"
        assert Layer.ENV == "env"
        assert Layer.DEFAULTS == "defaults"

    def test_layer_is_string_subclass(self) -> None:
        assert isinstance(Layer.APP, str)

    def test_layer_can_be_used_as_dict_key(self) -> None:
        data = {Layer.APP: "value"}
        assert data[Layer.APP] == "value"
        assert data["app"] == "value"

    def test_all_layers_defined(self) -> None:
        expected = {"defaults", "app", "host", "user", "dotenv", "env"}
        actual = {layer.value for layer in Layer}
        assert actual == expected


class TestValidateProfile:
    """Tests for validate_profile function.

    Profile names become directory segments like ``profile/{name}/``.
    The function accepts None (no profile) or validates the string.
    """

    # ========== NONE HANDLING ==========

    def test_returns_none_when_none(self) -> None:
        """None input should return None (no profile)."""
        assert validate_profile(None) is None

    # ========== VALID PROFILES ==========

    @pytest.mark.parametrize(
        "value",
        [
            "test",
            "dev",
            "staging",
            "production",
            "prod",
            "prod-v1",
            "staging_env",
            "production123",
            "v1",
            "v1.2",
            "my-custom-profile",
            "TEST",
            "Production",
        ],
    )
    def test_accepts_valid_profiles(self, value: str) -> None:
        """Valid profile names should pass through unchanged."""
        assert validate_profile(value) == value

    # ========== INVALID PROFILES ==========

    @pytest.mark.parametrize(
        "value,error_pattern",
        [
            ("", "profile cannot be empty"),
            ("../etc", "profile contains invalid characters"),
            ("..\\windows", "profile contains invalid characters"),
            ("/bad", "profile contains invalid characters"),
            (".hidden", "profile cannot start with a dot"),
            ("-profile", "profile must start with an alphanumeric"),
            ("_profile", "profile must start with an alphanumeric"),
            ("profile.", "profile cannot end with a dot"),
            ("tëst", "profile contains non-ASCII"),
            ("profile🚀", "profile contains non-ASCII"),
            ("CON", "profile is a Windows reserved name"),
            ("prn", "profile is a Windows reserved name"),
            ("my profile", "profile contains invalid characters"),
            ("profile<test>", "profile contains invalid characters"),
        ],
    )
    def test_rejects_invalid_profiles(self, value: str, error_pattern: str) -> None:
        """Invalid profile names should raise ValueError with descriptive message."""
        with pytest.raises(ValueError, match=error_pattern):
            validate_profile(value)

    # ========== LENGTH LIMITS ==========

    def test_accepts_profile_at_default_max_length(self) -> None:
        """Profile exactly at default max length should be accepted."""
        profile = "a" * DEFAULT_MAX_PROFILE_LENGTH
        assert validate_profile(profile) == profile

    def test_rejects_profile_exceeding_default_max_length(self) -> None:
        """Profile exceeding default max length should be rejected."""
        profile = "a" * (DEFAULT_MAX_PROFILE_LENGTH + 1)
        with pytest.raises(ValueError, match=f"profile exceeds maximum length of {DEFAULT_MAX_PROFILE_LENGTH}"):
            validate_profile(profile)

    def test_custom_max_length_accepts_shorter_profile(self) -> None:
        """Profile within custom max length should be accepted."""
        profile = "a" * 20
        assert validate_profile(profile, max_length=20) == profile

    def test_custom_max_length_rejects_longer_profile(self) -> None:
        """Profile exceeding custom max length should be rejected."""
        profile = "a" * 21
        with pytest.raises(ValueError, match="profile exceeds maximum length of 20"):
            validate_profile(profile, max_length=20)

    def test_zero_max_length_uses_absolute_max(self) -> None:
        """Setting max_length=0 should use ABSOLUTE_MAX_PROFILE_LENGTH (256)."""
        # Should accept up to 256 chars
        profile = "a" * 256
        assert validate_profile(profile, max_length=0) == profile
        # Should reject above 256 chars
        profile = "a" * 257
        with pytest.raises(ValueError, match="profile exceeds maximum length of 256"):
            validate_profile(profile, max_length=0)

    def test_negative_max_length_uses_absolute_max(self) -> None:
        """Setting max_length to negative should use ABSOLUTE_MAX_PROFILE_LENGTH (256)."""
        # Should accept up to 256 chars
        profile = "a" * 256
        assert validate_profile(profile, max_length=-1) == profile
        # Should reject above 256 chars
        profile = "a" * 257
        with pytest.raises(ValueError, match="profile exceeds maximum length of 256"):
            validate_profile(profile, max_length=-1)

    # ========== CONTROL CHARACTER REJECTION ==========

    @pytest.mark.parametrize(
        "char,name",
        [
            ("\x00", "null byte"),
            ("\x01", "SOH"),
            ("\x0a", "newline"),
            ("\x0d", "carriage return"),
            ("\x09", "tab"),
            ("\x1f", "unit separator"),
            ("\x7f", "DEL"),
        ],
    )
    def test_rejects_control_characters(self, char: str, name: str) -> None:
        """Control characters should be rejected."""
        with pytest.raises(ValueError, match="profile contains control characters"):
            validate_profile(f"test{char}profile")


class TestValidateProfileName:
    """Tests for validate_profile_name function.

    This is the public API for profile validation with configurable length.
    """

    # ========== VALID PROFILE NAMES ==========

    @pytest.mark.parametrize(
        "value",
        [
            "production",
            "test",
            "dev",
            "staging",
            "prod-v1",
            "test_env",
            "v1.2.3",
            "my-custom-profile",
        ],
    )
    def test_accepts_valid_profile_names(self, value: str) -> None:
        """Valid profile names should pass through unchanged."""
        assert validate_profile_name(value) == value

    # ========== SECURITY CHECKS ==========

    def test_rejects_empty_string(self) -> None:
        """Empty profile name should be rejected."""
        with pytest.raises(ValueError, match="profile cannot be empty"):
            validate_profile_name("")

    @pytest.mark.parametrize(
        "value",
        [
            "../etc/passwd",
            "..\\windows\\system32",
            "/etc/passwd",
            "\\windows\\system32",
            "foo/bar",
            "foo\\bar",
        ],
    )
    def test_rejects_path_traversal(self, value: str) -> None:
        """Path traversal attempts should be rejected."""
        with pytest.raises(ValueError, match="profile contains invalid characters"):
            validate_profile_name(value)

    @pytest.mark.parametrize(
        "value",
        [
            "test\x00inject",
            "test\nprofile",
            "test\rprofile",
            "test\tprofile",
        ],
    )
    def test_rejects_control_characters(self, value: str) -> None:
        """Control characters should be rejected."""
        with pytest.raises(ValueError, match="profile contains control characters"):
            validate_profile_name(value)

    def test_rejects_non_ascii(self) -> None:
        """Non-ASCII characters should be rejected."""
        with pytest.raises(ValueError, match="profile contains non-ASCII"):
            validate_profile_name("tëst")

    @pytest.mark.parametrize(
        "value",
        ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"],
    )
    def test_rejects_windows_reserved_names(self, value: str) -> None:
        """Windows reserved names should be rejected."""
        with pytest.raises(ValueError, match="profile is a Windows reserved name"):
            validate_profile_name(value)

    # ========== LENGTH LIMITS ==========

    def test_default_max_length_is_64(self) -> None:
        """Default max length should be 64 characters."""
        assert DEFAULT_MAX_PROFILE_LENGTH == 64

    def test_accepts_exactly_64_characters(self) -> None:
        """Profile with exactly 64 characters should be accepted."""
        profile = "a" * 64
        assert validate_profile_name(profile) == profile

    def test_rejects_65_characters(self) -> None:
        """Profile with 65 characters should be rejected."""
        profile = "a" * 65
        with pytest.raises(ValueError, match="profile exceeds maximum length of 64: 65 characters"):
            validate_profile_name(profile)

    def test_custom_max_length(self) -> None:
        """Custom max length should be respected."""
        profile = "a" * 10
        assert validate_profile_name(profile, max_length=10) == profile

        profile = "a" * 11
        with pytest.raises(ValueError, match="profile exceeds maximum length of 10: 11 characters"):
            validate_profile_name(profile, max_length=10)

    def test_zero_max_length_uses_absolute_max(self) -> None:
        """max_length=0 should use the absolute max (256 chars)."""
        # Up to 256 chars should pass
        assert validate_profile_name("a" * 256, max_length=0) == "a" * 256
        # Above 256 chars should fail
        with pytest.raises(ValueError, match="profile exceeds maximum length of 256"):
            validate_profile_name("a" * 257, max_length=0)

    def test_negative_max_length_uses_absolute_max(self) -> None:
        """Negative max_length should use the absolute max (256 chars)."""
        # Up to 256 chars should pass
        assert validate_profile_name("a" * 256, max_length=-1) == "a" * 256
        # Above 256 chars should fail
        with pytest.raises(ValueError, match="profile exceeds maximum length of 256"):
            validate_profile_name("a" * 257, max_length=-1)


class TestIsValidProfileName:
    """Tests for is_valid_profile_name function.

    This function returns bool instead of raising exceptions.
    """

    # ========== VALID PROFILES ==========

    def test_none_is_valid(self) -> None:
        """None should be considered valid (no profile)."""
        assert is_valid_profile_name(None) is True

    @pytest.mark.parametrize(
        "value",
        [
            "production",
            "test",
            "dev",
            "staging",
            "prod-v1",
            "test_env",
            "v1.2.3",
        ],
    )
    def test_valid_profiles_return_true(self, value: str) -> None:
        """Valid profile names should return True."""
        assert is_valid_profile_name(value) is True

    # ========== INVALID PROFILES ==========

    @pytest.mark.parametrize(
        "value",
        [
            "",  # Empty
            "../etc",  # Path traversal
            "test\x00inject",  # Control character
            "tëst",  # Non-ASCII
            "CON",  # Windows reserved
            ".hidden",  # Starts with dot
            "-profile",  # Starts with hyphen
            "profile.",  # Ends with dot
            "my profile",  # Contains space
        ],
    )
    def test_invalid_profiles_return_false(self, value: str) -> None:
        """Invalid profile names should return False."""
        assert is_valid_profile_name(value) is False

    # ========== LENGTH LIMITS ==========

    def test_length_at_limit_returns_true(self) -> None:
        """Profile at default length limit should return True."""
        profile = "a" * DEFAULT_MAX_PROFILE_LENGTH
        assert is_valid_profile_name(profile) is True

    def test_length_exceeds_limit_returns_false(self) -> None:
        """Profile exceeding default length limit should return False."""
        profile = "a" * (DEFAULT_MAX_PROFILE_LENGTH + 1)
        assert is_valid_profile_name(profile) is False

    def test_custom_max_length(self) -> None:
        """Custom max length should be respected."""
        profile = "a" * 100
        assert is_valid_profile_name(profile, max_length=100) is True
        assert is_valid_profile_name(profile, max_length=50) is False

    def test_zero_max_length_uses_absolute_max(self) -> None:
        """max_length=0 should use the absolute max (256 chars)."""
        # Up to 256 chars should be valid
        assert is_valid_profile_name("a" * 256, max_length=0) is True
        # Above 256 chars should be invalid
        assert is_valid_profile_name("a" * 257, max_length=0) is False

    def test_negative_max_length_uses_absolute_max(self) -> None:
        """Negative max_length should use the absolute max (256 chars)."""
        # Up to 256 chars should be valid
        assert is_valid_profile_name("a" * 256, max_length=-1) is True
        # Above 256 chars should be invalid
        assert is_valid_profile_name("a" * 257, max_length=-1) is False


class TestDefaultMaxProfileLength:
    """Tests for DEFAULT_MAX_PROFILE_LENGTH constant."""

    def test_value_is_64(self) -> None:
        """Default max profile length should be 64."""
        assert DEFAULT_MAX_PROFILE_LENGTH == 64

    def test_is_immutable_int(self) -> None:
        """Constant should be an integer."""
        assert isinstance(DEFAULT_MAX_PROFILE_LENGTH, int)


class TestAbsoluteMaxProfileLength:
    """Tests for ABSOLUTE_MAX_PROFILE_LENGTH constant and clamping behavior.

    The absolute maximum is a security hardening measure that prevents
    filesystem issues from excessively long path segments. Even if users
    set max_length higher than 256, the absolute limit is enforced.
    """

    def test_value_is_256(self) -> None:
        """Absolute max profile length should be 256."""
        assert ABSOLUTE_MAX_PROFILE_LENGTH == 256

    def test_is_immutable_int(self) -> None:
        """Constant should be an integer."""
        assert isinstance(ABSOLUTE_MAX_PROFILE_LENGTH, int)

    def test_accepts_profile_at_absolute_max_length(self) -> None:
        """Profile exactly at absolute max length (256) should be accepted."""
        profile = "a" * 256
        assert validate_profile_name(profile, max_length=1000) == profile

    def test_rejects_profile_exceeding_absolute_max_length(self) -> None:
        """Profile exceeding absolute max (257 chars) should be rejected even with max_length=1000."""
        profile = "a" * 257
        with pytest.raises(ValueError, match="profile exceeds maximum length of 256: 257 characters"):
            validate_profile_name(profile, max_length=1000)

    def test_max_length_clamped_to_absolute_max(self) -> None:
        """Setting max_length=1000 should effectively use 256."""
        # 256 chars should pass
        assert validate_profile_name("a" * 256, max_length=1000) == "a" * 256
        # 257 chars should fail with message showing 256 as the limit
        with pytest.raises(ValueError, match="profile exceeds maximum length of 256"):
            validate_profile_name("a" * 257, max_length=1000)

    def test_zero_max_length_still_enforces_absolute_max(self) -> None:
        """max_length=0 should still enforce the 256 char absolute maximum."""
        # Previously max_length=0 disabled length checking entirely
        # Now it should still enforce the absolute maximum
        profile = "a" * 256
        assert validate_profile_name(profile, max_length=0) == profile

        profile = "a" * 257
        with pytest.raises(ValueError, match="profile exceeds maximum length of 256: 257 characters"):
            validate_profile_name(profile, max_length=0)

    def test_negative_max_length_still_enforces_absolute_max(self) -> None:
        """Negative max_length should still enforce the 256 char absolute maximum."""
        profile = "a" * 256
        assert validate_profile_name(profile, max_length=-1) == profile

        profile = "a" * 257
        with pytest.raises(ValueError, match="profile exceeds maximum length of 256: 257 characters"):
            validate_profile_name(profile, max_length=-1)

    def test_is_valid_profile_name_respects_absolute_max(self) -> None:
        """is_valid_profile_name should also respect the absolute maximum."""
        # At absolute max
        assert is_valid_profile_name("a" * 256, max_length=1000) is True
        # Above absolute max
        assert is_valid_profile_name("a" * 257, max_length=1000) is False
        # With max_length=0 (previously disabled checking)
        assert is_valid_profile_name("a" * 256, max_length=0) is True
        assert is_valid_profile_name("a" * 257, max_length=0) is False

    def test_validate_profile_respects_absolute_max(self) -> None:
        """validate_profile should also respect the absolute maximum."""
        # At absolute max
        assert validate_profile("a" * 256, max_length=1000) == "a" * 256
        # Above absolute max
        with pytest.raises(ValueError, match="profile exceeds maximum length of 256"):
            validate_profile("a" * 257, max_length=1000)
