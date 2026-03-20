"""
Story Forge - Self-Publishing Dashboard
Main entry point for the NiceGUI application.
"""

import os
import asyncio
from pathlib import Path

import auth
from db import init_db, get_session

# Configure environment
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

# Application configuration
APP_TITLE = "Story Forge"
APP_VERSION = "0.1.0"


def create_app():
    """Create and configure the NiceGUI application."""
    import nicegui as ui
    
    # Initialize database
    init_db()
    
    @ui.page("/")
    def home_page():
        """Home page - redirect to login or dashboard."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
        else:
            ui.navigate.to("/dashboard")
    
    @ui.page("/login")
    def login_page():
        """Login page with Google OAuth."""
        # If already authenticated, redirect to dashboard
        if auth.is_authenticated():
            ui.navigate.to("/dashboard")
            return
        
        with ui.column().classes("w-full h-screen justify-center items-center"):
            with ui.card().classes("w-96 p-8"):
                ui.label(APP_TITLE).classes("text-3xl font-bold text-center")
                ui.label(f"Version {APP_VERSION}").classes("text-sm text-gray-500 text-center")
                
                ui.separator()
                
                ui.label("Sign in to continue").classes("text-lg text-center mt-4")
                
                # Login button
                def go_to_google():
                    login_url = auth.get_login_url()
                    ui.navigate.to(login_url, new_tab=True)
                
                ui.button(
                    "Sign in with Google",
                    on_click=go_to_google,
                    icon="login"
                ).classes("w-full mt-4")
                
                ui.label(
                    "Secure authentication powered by Google OAuth 2.0"
                ).classes("text-xs text-gray-400 text-center mt-4")
    
    @ui.page("/auth/callback")
    def auth_callback_page():
        """OAuth callback handler."""
        
        # Get query parameters
        query = ui.query_params
        code = query.get("code")
        state = query.get("state")
        error = query.get("error")
        
        if error:
            ui.notify(f"Authentication error: {error}", type="negative")
            ui.navigate.to("/login")
            return
        
        if not code or not state:
            ui.notify("Missing authentication parameters", type="negative")
            ui.navigate.to("/login")
            return
        
        # Validate state
        if not auth.validate_state(state):
            ui.notify("Invalid state parameter", type="negative")
            ui.navigate.to("/login")
            return
        
        # Show loading
        with ui.column().classes("w-full h-screen justify-center items-center"):
            ui.spinner(size="lg")
            ui.label("Completing sign in...").classes("mt-4")
        
        # Process OAuth callback
        async def process_callback():
            try:
                db = get_session()
                await auth.handle_oauth_callback(db, code)
                db.close()
                
                ui.notify("Successfully signed in!", type="positive")
                ui.navigate.to("/dashboard")
            except Exception as e:
                ui.notify(f"Sign in failed: {str(e)}", type="negative")
                ui.navigate.to("/login")
        
        # Run async callback
        asyncio.create_task(process_callback())
    
    @ui.page("/logout")
    def logout_page():
        """Logout handler."""
        auth.logout()
        ui.notify("You have been signed out", type="info")
        ui.navigate.to("/login")
    
    @ui.page("/dashboard")
    def dashboard_page():
        """Dashboard page - requires authentication."""
        # Check authentication
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return
        
        user_name = auth.get_session("user_name", "User")
        user_email = auth.get_session("user_email", "")
        user_avatar = auth.get_session("user_avatar", "")
        
        # Header with user info
        with ui.header().classes("bg-white shadow"):
            with ui.row().classes("w-full justify-between items-center px-4"):
                ui.label(APP_TITLE).classes("text-xl font-bold")
                
                with ui.row().classes("items-center gap-4"):
                    # User avatar and email
                    if user_avatar:
                        ui.avatar(
                            source=user_avatar,
                            size="sm"
                        )
                    ui.label(user_email).classes("text-sm text-gray-600")
                    ui.button(
                        "Logout",
                        on_click=lambda: ui.navigate.to("/logout"),
                        icon="logout"
                    ).props("flat dense")
        
        # Dashboard content
        with ui.column().classes("w-full max-w-4xl mx-auto p-8"):
            ui.label(f"Welcome, {user_name}!").classes("text-3xl font-bold")
            ui.label("Your publishing overview").classes("text-gray-500")
            
            with ui.row().classes("mt-8 gap-4"):
                with ui.card().classes("p-4"):
                    ui.label("Books").classes("text-lg font-semibold")
                    ui.label("0").classes("text-4xl font-bold text-blue-600")
                    ui.label("in library").classes("text-sm text-gray-500")
                
                with ui.card().classes("p-4"):
                    ui.label("Chapters").classes("text-lg font-semibold")
                    ui.label("0").classes("text-4xl font-bold text-green-600")
                    ui.label("written").classes("text-sm text-gray-500")
                
                with ui.card().classes("p-4"):
                    ui.label("Audiobooks").classes("text-lg font-semibold")
                    ui.label("0").classes("text-4xl font-bold text-purple-600")
                    ui.label("generated").classes("text-sm text-gray-500")
            
            with ui.card().classes("mt-8 p-4"):
                ui.label("Quick Actions").classes("text-lg font-semibold")
                with ui.row().classes("mt-4 gap-4"):
                    ui.button("New Book", icon="add", on_click=lambda: ui.navigate.to("/books"))
                    ui.button("View Books", icon="library_books", on_click=lambda: ui.navigate.to("/books"))
    
    @ui.page("/books")
    def books_page():
        """Books management page - requires authentication."""
        # Check authentication
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return
        
        # Header with user info
        with ui.header().classes("bg-white shadow"):
            with ui.row().classes("w-full justify-between items-center px-4"):
                ui.label(APP_TITLE).classes("text-xl font-bold")
                
                with ui.row().classes("items-center gap-4"):
                    ui.button(
                        "Dashboard",
                        on_click=lambda: ui.navigate.to("/dashboard"),
                        icon="dashboard"
                    ).props("flat dense")
                    ui.button(
                        "Logout",
                        on_click=lambda: ui.navigate.to("/logout"),
                        icon="logout"
                    ).props("flat dense")
        
        # Books content
        with ui.column().classes("w-full max-w-4xl mx-auto p-8"):
            with ui.row().classes("justify-between items-center"):
                ui.label("Books").classes("text-3xl font-bold")
                ui.button("New Book", icon="add")
            
            with ui.card().classes("mt-8"):
                ui.label("Your Book Library").classes("text-lg font-semibold")
                ui.label("No books yet. Create your first book to get started!").classes("mt-2 text-gray-600")


def main():
    """Main entry point."""
    import nicegui as ui
    
    # Create the app
    create_app()
    
    # Configure UI
    ui.config.title = APP_TITLE
    ui.config.reload = False  # Disable auto-reload for production
    
    # Run the app
    port = int(os.environ.get("PORT", "8080"))
    ui.run(host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
