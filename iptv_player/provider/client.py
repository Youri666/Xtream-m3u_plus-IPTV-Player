"""HTTP client for the Xtream Codes provider API."""

CONNECTION_HEADER = "Keep-Alive"
CONTENT_HEADER = "gzip, deflate"
DEFAULT_USER_AGENT_HEADER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)


def provider_headers(user_agent=None):
    """Return consistent headers for every provider request."""
    return {
        "Connection": CONNECTION_HEADER,
        "Accept-Encoding": CONTENT_HEADER,
        "User-Agent": str(user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER,
    }


class XtreamClient:
    """Make authenticated requests through one reusable HTTP session."""

    def __init__(
        self,
        server,
        username,
        password,
        user_agent=None,
        timeout=(3, 30),
        session=None,
    ):
        self.api_url = f"{str(server).rstrip('/')}/player_api.php"
        self.username = username
        self.password = password
        self.timeout = timeout
        self._owns_session = session is None
        if session is None:
            # Import lazily so pure client tests can inject a session without
            # requiring the network dependency to be installed.
            import requests

            session = requests.Session()
        self.session = session
        self.headers = provider_headers(user_agent)

    def get_json(self, action="", **parameters):
        """Request one API action and return its decoded JSON response."""
        request_parameters = {
            "username": self.username,
            "password": self.password,
            "action": action,
        }
        request_parameters.update(parameters)
        response = self.session.get(
            self.api_url,
            params=request_parameters,
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def close(self):
        """Close a session created by this client."""
        if self._owns_session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
