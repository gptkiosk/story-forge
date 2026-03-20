"""
Story Forge - Self-Publishing Dashboard
Main entry point for the NiceGUI application.
"""

import os
from pathlib import Path

# Configure environment
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

# Application configuration
APP_TITLE = "Story Forge"
APP_VERSION = "0.1.0"


def create_app():
    """Create and configure the NiceGUI application."""
    import nicegui as ui
    
    @ui.page("/")
    def home_page():
        """Home/Dashboard page."""
        with ui.column().classes("w-full max-w-4xl mx-auto p-8"):
            ui.label(APP_TITLE).classes("text-3xl font-bold")
            ui.label(f"Version {APP_VERSION}").classes("text-sm text-gray-500")
            
            with ui.card().classes("mt-8"):
                ui.label("Welcome to Story Forge").classes("text-xl font-semibold")
                ui.label(
                    "Your self-publishing dashboard for managing books, chapters, "
                    "and audiobook generation."
                ).classes("mt-2 text-gray-600")
                
                with ui.row().classes("mt-4 gap-4"):
                    ui.button("Dashboard", on_click=lambda: ui.navigate.to("/dashboard"))
                    ui.button("Books", on_click=lambda: ui.navigate.to("/books"))
    
    @ui.page("/dashboard")
    def dashboard_page():
        """Dashboard page showing overview."""
        with ui.column().classes("w-full max-w-4xl mx-auto p-8"):
            ui.label("Dashboard").classes("text-3xl font-bold")
            ui.label("Overview of your publishing projects").classes("text-gray-500")
            
            # Placeholder for future dashboard content
            with ui.card().classes("mt-8"):
                ui.label("Coming Soon").classes("text-lg font-semibold")
                ui.label("Dashboard analytics and recent activity will appear here.")
    
    @ui.page("/books")
    def books_page():
        """Books management page."""
        with ui.column().classes("w-full max-w-4xl mx-auto p-8"):
            ui.label("Books").classes("text-3xl font-bold")
            ui.label("Manage your book projects").classes("text-gray-500")
            
            # Placeholder for future books list
            with ui.card().classes("mt-8"):
                ui.label("Coming Soon").classes("text-lg font-semibold")
                ui.label("Your book library will appear here.")
    
    return ui


def main():
    """Main entry point."""
    import nicegui as ui
    
    # Create the app
    app = create_app()
    
    # Configure UI
    ui.config.title = APP_TITLE
    ui.config.reload = False  # Disable auto-reload for production
    
    # Run the app
    port = int(os.environ.get("PORT", "8080"))
    ui.run(host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
