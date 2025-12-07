"""
Configuration Endpoint
Serves the configuration UI
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.core.config import settings

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
@router.get("/configure", response_class=HTMLResponse)
async def configure_page():
    """Serve configuration page"""
    
    # Get server defaults for API keys
    tmdb_default = settings.TMDB_API_KEY or ""
    mdblist_default = settings.MDBLIST_API_KEY or ""
    
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dynamic Recommendations - Configure</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 600px;
            width: 100%;
            padding: 40px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
            font-size: 14px;
        }
        input[type="text"],
        input[type="number"] {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        .checkbox-group {
            display: flex;
            align-items: center;
            margin-top: 10px;
        }
        input[type="checkbox"] {
            margin-right: 8px;
            width: 18px;
            height: 18px;
            cursor: pointer;
        }
        .checkbox-group label {
            margin-bottom: 0;
            cursor: pointer;
            font-weight: normal;
        }
        .helper-text {
            font-size: 12px;
            color: #999;
            margin-top: 4px;
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .install-url {
            margin-top: 30px;
            padding: 20px;
            background: #f5f5f5;
            border-radius: 8px;
            display: none;
        }
        .install-url.visible {
            display: block;
        }
        .install-url h3 {
            color: #333;
            margin-bottom: 10px;
            font-size: 16px;
        }
        .url-box {
            background: white;
            padding: 12px;
            border-radius: 6px;
            word-break: break-all;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            border: 1px solid #ddd;
            margin-bottom: 10px;
        }
        .copy-button {
            background: #4CAF50;
            padding: 10px;
            font-size: 14px;
        }
        .copy-button:hover {
            background: #45a049;
        }
        .error {
            color: #d32f2f;
            font-size: 14px;
            margin-top: 10px;
            display: none;
        }
        .error.visible {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 Dynamic Recommendations</h1>
        <p class="subtitle">Configure your personalized Stremio addon</p>
        
        <form id="configForm">
            <div class="form-group">
                <label for="stremio_auth">Stremio Auth Key *</label>
                <input type="text" id="stremio_auth" required 
                       placeholder="Your Stremio authentication key">
                <div class="helper-text">Required to access your watch history</div>
            </div>
            
            <div class="form-group">
                <label for="tmdb_key">TMDB API Key *</label>
                <input type="text" id="tmdb_key" required
                       placeholder="Your TMDB API key" value="__TMDB_DEFAULT__">
                <div class="helper-text">Required - Get one free at themoviedb.org/settings/api</div>
            </div>
            
            <div class="form-group">
                <label for="mdblist_key">MDBList API Key *</label>
                <input type="text" id="mdblist_key" required
                       placeholder="Your MDBList API key" value="__MDBLIST_DEFAULT__">
                <div class="helper-text">Required - Get one at mdblist.com/api</div>
            </div>
            
            <div class="form-group">
                <label for="num_rows">Number of Recommendation Rows</label>
                <input type="number" id="num_rows" min="1" max="20" value="5">
                <div class="helper-text">How many "Because you watched X" rows to show</div>
            </div>
            
            <div class="form-group">
                <label for="min_rating">Minimum Rating Filter</label>
                <input type="number" id="min_rating" min="0" max="10" step="0.1" value="6.0">
                <div class="helper-text">Only show content with this rating or higher</div>
            </div>
            
            <div class="form-group">
                <div class="checkbox-group">
                    <input type="checkbox" id="use_loved" checked>
                    <label for="use_loved">Prioritize loved items over watch history</label>
                </div>
            </div>
            
            <div class="form-group">
                <div class="checkbox-group">
                    <input type="checkbox" id="include_movies" checked>
                    <label for="include_movies">Include movies</label>
                </div>
            </div>
            
            <div class="form-group">
                <div class="checkbox-group">
                    <input type="checkbox" id="include_series" checked>
                    <label for="include_series">Include series</label>
                </div>
            </div>
            
            <button type="submit">Generate Install URL</button>
            
            <div class="error" id="error"></div>
        </form>
        
        <div class="install-url" id="installUrl">
            <h3>✅ Install URL Generated</h3>
            <div class="url-box" id="urlBox"></div>
            <button class="copy-button" onclick="copyUrl()">Copy to Clipboard</button>
            <div class="helper-text" style="margin-top: 10px;">
                Copy this URL and add it to Stremio via "Add-ons" → "Install from URL"
            </div>
        </div>
    </div>
    
    <script>
        const form = document.getElementById('configForm');
        const installDiv = document.getElementById('installUrl');
        const urlBox = document.getElementById('urlBox');
        const errorDiv = document.getElementById('error');
        
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const config = {
                stremio_auth_key: document.getElementById('stremio_auth').value.trim(),
                tmdb_api_key: document.getElementById('tmdb_key').value.trim(),
                mdblist_api_key: document.getElementById('mdblist_key').value.trim(),
                num_rows: parseInt(document.getElementById('num_rows').value),
                min_rating: parseFloat(document.getElementById('min_rating').value),
                use_loved_items: document.getElementById('use_loved').checked,
                include_movies: document.getElementById('include_movies').checked,
                include_series: document.getElementById('include_series').checked
            };
            
            if (!config.stremio_auth_key) {
                showError('Stremio Auth Key is required');
                return;
            }
            
            if (!config.tmdb_api_key) {
                showError('TMDB API Key is required');
                return;
            }
            
            if (!config.mdblist_api_key) {
                showError('MDBList API Key is required');
                return;
            }
            
            try {
                // Encode config
                const configJson = JSON.stringify(config);
                const token = btoa(configJson);
                
                // Generate install URL
                const baseUrl = window.location.origin;
                const installUrl = `${baseUrl}/${token}/manifest.json`;
                
                urlBox.textContent = installUrl;
                installDiv.classList.add('visible');
                errorDiv.classList.remove('visible');
                
                // Store for copy function
                window.currentUrl = installUrl;
            } catch (err) {
                showError('Failed to generate URL: ' + err.message);
            }
        });
        
        function copyUrl() {
            if (window.currentUrl) {
                navigator.clipboard.writeText(window.currentUrl).then(() => {
                    const btn = document.querySelector('.copy-button');
                    btn.textContent = '✓ Copied!';
                    setTimeout(() => {
                        btn.textContent = 'Copy to Clipboard';
                    }, 2000);
                });
            }
        }
        
        function showError(message) {
            errorDiv.textContent = message;
            errorDiv.classList.add('visible');
            installDiv.classList.remove('visible');
        }
    </script>
</body>
</html>
    """
    
    # Replace placeholders with actual values
    html_content = html_content.replace("__TMDB_DEFAULT__", tmdb_default)
    html_content = html_content.replace("__MDBLIST_DEFAULT__", mdblist_default)
    
    return html_content
