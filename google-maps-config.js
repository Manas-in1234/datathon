// ==============================================================================
// Citidy & CityFix AI — Client Configuration
// ==============================================================================

// Google Maps Embed API (Optional: street map fallback works with zero keys)
window.CITYFIX_GOOGLE_MAPS_EMBED_KEY = '';

// Backend API Base URL (Optional)
// - Leave empty ('') when running with local Python server (http://localhost:8000).
// - Set to remote API URL if deployed to a static host (e.g. GitHub Pages) with a hosted backend:
//   window.CITIDY_API_BASE_URL = 'https://your-citidy-backend.onrender.com';
window.CITIDY_API_BASE_URL = '';

// Supabase Cloud Configuration (Optional)
// If you want to use Supabase Auth and PostgreSQL directly from the browser:
window.CITIDY_SUPABASE_URL = '';
window.CITIDY_SUPABASE_ANON_KEY = '';
