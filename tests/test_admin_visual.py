"""
Visual tests for Django Admin using Playwright.

These tests verify that the admin interface is accessible and displays correctly.
"""

import os
import subprocess
import time
import signal
from playwright.sync_api import sync_playwright, expect


class DjangoTestServer:
    """Context manager to start/stop Django test server."""

    def __init__(self, port=8000):
        self.port = port
        self.process = None

    def __enter__(self):
        """Start Django development server."""
        self.process = subprocess.Popen(
            ['python', 'manage.py', 'runserver', str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        # Wait for server to start
        time.sleep(3)
        return f'http://localhost:{self.port}'

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop Django development server."""
        if self.process:
            if os.name == 'nt':
                # Windows
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
                time.sleep(1)
                self.process.kill()
            else:
                # Unix
                self.process.terminate()
            self.process.wait()


def test_admin_login_page_visual():
    """
    TEST TYPE: VISUAL
    Verify Django admin login page displays correctly.
    """
    with DjangoTestServer() as base_url:
        with sync_playwright() as p:
            # Launch browser
            browser = p.chromium.launch(headless=False)  # Set to True for CI
            context = browser.new_context()
            page = context.new_page()

            try:
                # Navigate to admin login
                admin_url = f'{base_url}/admin/'
                print(f"Navigating to: {admin_url}")
                page.goto(admin_url)

                # Wait for page to load
                page.wait_for_load_state('networkidle')

                # Take screenshot for visual verification
                screenshot_path = 'tests/screenshots/admin_login.png'
                os.makedirs('tests/screenshots', exist_ok=True)
                page.screenshot(path=screenshot_path)
                print(f"Screenshot saved: {screenshot_path}")

                # Visual assertions
                # 1. Check title
                expect(page).to_have_title('Log in | Django site admin')
                print("✓ Title correct")

                # 2. Check login form exists
                expect(page.locator('#login-form')).to_be_visible()
                print("✓ Login form visible")

                # 3. Check username field
                username_field = page.locator('#id_username')
                expect(username_field).to_be_visible()
                expect(username_field).to_be_editable()
                print("✓ Username field present and editable")

                # 4. Check password field
                password_field = page.locator('#id_password')
                expect(password_field).to_be_visible()
                expect(password_field).to_be_editable()
                expect(password_field).to_have_attribute('type', 'password')
                print("✓ Password field present and masked")

                # 5. Check login button
                login_button = page.locator('input[type="submit"]')
                expect(login_button).to_be_visible()
                expect(login_button).to_be_enabled()
                print("✓ Login button visible and enabled")

                # 6. Check Django branding
                expect(page.locator('#header')).to_be_visible()
                print("✓ Django admin header visible")

                print("\n✅ Admin login page visual test PASSED")

            finally:
                context.close()
                browser.close()


def test_admin_dashboard_after_login_visual():
    """
    TEST TYPE: VISUAL + FUNCTIONAL
    Verify admin can login and see dashboard.
    """
    with DjangoTestServer() as base_url:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            try:
                # Navigate to admin
                admin_url = f'{base_url}/admin/'
                print(f"Navigating to: {admin_url}")
                page.goto(admin_url)
                page.wait_for_load_state('networkidle')

                # Login
                print("Attempting login...")
                page.fill('#id_username', 'admin@ayni.cl')
                page.fill('#id_password', 'gabe123123')
                page.click('input[type="submit"]')

                # Wait for dashboard
                page.wait_for_load_state('networkidle')
                time.sleep(1)  # Extra wait for any JS

                # Take screenshot
                screenshot_path = 'tests/screenshots/admin_dashboard.png'
                page.screenshot(path=screenshot_path)
                print(f"Screenshot saved: {screenshot_path}")

                # Visual assertions
                # 1. Check we're on dashboard
                expect(page).to_have_url(f'{base_url}/admin/')
                print("✓ Redirected to dashboard")

                # 2. Check welcome message
                expect(page.locator('#user-tools')).to_contain_text('admin@ayni.cl')
                print("✓ User logged in (email displayed)")

                # 3. Check our custom apps are visible
                # Authentication app
                auth_section = page.locator('text=Authentication')
                expect(auth_section).to_be_visible()
                print("✓ Authentication app visible")

                # Companies app
                companies_section = page.locator('text=Companies')
                expect(companies_section).to_be_visible()
                print("✓ Companies app visible")

                # Processing app
                processing_section = page.locator('text=Processing')
                expect(processing_section).to_be_visible()
                print("✓ Processing app visible")

                # Analytics app
                analytics_section = page.locator('text=Analytics')
                expect(analytics_section).to_be_visible()
                print("✓ Analytics app visible")

                # 4. Check specific models are listed
                expect(page.locator('text=Users')).to_be_visible()
                expect(page.locator('text=Companys')).to_be_visible()  # Note: Django pluralizes
                print("✓ Model links visible")

                # 5. Click into Users model
                page.click('a.section:has-text("Authentication") + table a:has-text("Users")')
                page.wait_for_load_state('networkidle')

                # Screenshot of Users list
                screenshot_path = 'tests/screenshots/admin_users_list.png'
                page.screenshot(path=screenshot_path)
                print(f"Screenshot saved: {screenshot_path}")

                # Check we're on users page
                expect(page).to_have_url(f'{base_url}/admin/authentication/user/')
                expect(page.locator('h1')).to_contain_text('Select user to change')
                print("✓ Users list page loaded")

                # Check admin user is listed
                expect(page.locator('text=admin@ayni.cl')).to_be_visible()
                print("✓ Admin user visible in list")

                print("\n✅ Admin dashboard visual test PASSED")

            finally:
                context.close()
                browser.close()


def test_admin_create_company_visual():
    """
    TEST TYPE: VISUAL + FUNCTIONAL
    Verify admin can create a company through the UI.
    """
    with DjangoTestServer() as base_url:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            try:
                # Login
                admin_url = f'{base_url}/admin/'
                page.goto(admin_url)
                page.wait_for_load_state('networkidle')
                page.fill('#id_username', 'admin@ayni.cl')
                page.fill('#id_password', 'gabe123123')
                page.click('input[type="submit"]')
                page.wait_for_load_state('networkidle')

                # Navigate to Companies
                page.click('a.section:has-text("Companies") + table a:has-text("Companys")')
                page.wait_for_load_state('networkidle')

                # Click "Add Company"
                page.click('a.addlink:has-text("Add company")')
                page.wait_for_load_state('networkidle')

                # Screenshot of add form
                screenshot_path = 'tests/screenshots/admin_company_add.png'
                page.screenshot(path=screenshot_path)
                print(f"Screenshot saved: {screenshot_path}")

                # Fill in company details
                page.fill('#id_name', 'Test PYME Visual')
                page.fill('#id_rut', '12.345.678-9')
                page.select_option('#id_industry', 'retail')
                page.select_option('#id_size', 'micro')

                # Screenshot before save
                screenshot_path = 'tests/screenshots/admin_company_filled.png'
                page.screenshot(path=screenshot_path)
                print(f"Screenshot saved: {screenshot_path}")

                # Save
                page.click('input[name="_save"]')
                page.wait_for_load_state('networkidle')

                # Check success message
                expect(page.locator('.success')).to_contain_text('successfully added')
                print("✓ Company created successfully")

                # Screenshot of success
                screenshot_path = 'tests/screenshots/admin_company_success.png'
                page.screenshot(path=screenshot_path)
                print(f"Screenshot saved: {screenshot_path}")

                # Verify company is in list
                expect(page.locator('text=Test PYME Visual')).to_be_visible()
                expect(page.locator('text=12.345.678-9')).to_be_visible()
                print("✓ Company visible in list")

                print("\n✅ Create company visual test PASSED")

            finally:
                context.close()
                browser.close()


if __name__ == '__main__':
    """Run visual tests manually."""
    print("=" * 70)
    print("AYNI Backend - Django Admin Visual Tests")
    print("=" * 70)
    print()
    print("⚠️  IMPORTANT: Make sure to access via HTTP, not HTTPS!")
    print("    Correct: http://localhost:8000/admin/")
    print("    Wrong:   https://localhost:8000/admin/")
    print()
    print("=" * 70)
    print()

    try:
        print("TEST 1: Admin Login Page")
        print("-" * 70)
        test_admin_login_page_visual()
        print()

        print("TEST 2: Admin Dashboard After Login")
        print("-" * 70)
        test_admin_dashboard_after_login_visual()
        print()

        print("TEST 3: Create Company Via Admin")
        print("-" * 70)
        test_admin_create_company_visual()
        print()

        print("=" * 70)
        print("✅ ALL VISUAL TESTS PASSED!")
        print("=" * 70)
        print()
        print("📸 Screenshots saved in: tests/screenshots/")
        print("   - admin_login.png")
        print("   - admin_dashboard.png")
        print("   - admin_users_list.png")
        print("   - admin_company_add.png")
        print("   - admin_company_filled.png")
        print("   - admin_company_success.png")

    except Exception as e:
        print()
        print("=" * 70)
        print("❌ VISUAL TEST FAILED!")
        print("=" * 70)
        print(f"Error: {e}")
        raise
