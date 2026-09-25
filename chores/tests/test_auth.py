from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase, Client
from django.urls import reverse


class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='SecurePassword123!',
            first_name='Test',
            last_name='User'
        )

    def test_registration_success(self):
        """Guests can successfully register with valid details."""
        url = reverse('register')
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'first_name': 'New',
            'last_name': 'Member',
            'password1': 'StrongPassword789!',
            'password2': 'StrongPassword789!',
        }
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, reverse('login'))
        self.assertTrue(User.objects.filter(username='newuser').exists())

        new_user = User.objects.get(username='newuser')
        self.assertEqual(new_user.email, 'newuser@example.com')
        self.assertEqual(new_user.first_name, 'New')
        self.assertEqual(new_user.last_name, 'Member')

        # Check flash message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('created successfully' in str(m) for m in messages))

    def test_registration_duplicate_username(self):
        """Registration fails if username already exists."""
        url = reverse('register')
        data = {
            'username': 'testuser',
            'email': 'another@example.com',
            'password1': 'StrongPassword789!',
            'password2': 'StrongPassword789!',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'username', 'A user with that username already exists.')

    def test_registration_duplicate_email(self):
        """Registration fails if email is already associated with another user."""
        url = reverse('register')
        data = {
            'username': 'uniqueuser',
            'email': 'testuser@example.com',  # Existing email
            'password1': 'StrongPassword789!',
            'password2': 'StrongPassword789!',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'email', 'An account with this email address already exists.')

    def test_registration_password_mismatch(self):
        """Registration fails if passwords do not match."""
        url = reverse('register')
        data = {
            'username': 'mismatchuser',
            'email': 'mismatch@example.com',
            'password1': 'PasswordOne123!',
            'password2': 'PasswordTwo123!',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='mismatchuser').exists())

    def test_login_success(self):
        """Users can log in with valid credentials and receive feedback."""
        url = reverse('login')
        response = self.client.post(url, {
            'username': 'testuser',
            'password': 'SecurePassword123!',
        }, follow=True)

        self.assertRedirects(response, reverse('home'))
        self.assertTrue(response.context['user'].is_authenticated)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Welcome back, testuser' in str(m) for m in messages))

    def test_login_invalid_credentials(self):
        """Login fails with invalid credentials."""
        url = reverse('login')
        response = self.client.post(url, {
            'username': 'testuser',
            'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['user'].is_authenticated)

    def test_logout(self):
        """Users can log out, which terminates session and shows feedback message."""
        self.client.login(username='testuser', password='SecurePassword123!')
        url = reverse('logout')
        response = self.client.post(url, follow=True)

        self.assertRedirects(response, reverse('login'))
        self.assertFalse(response.context['user'].is_authenticated)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('You have been logged out.' in str(m) for m in messages))

    def test_logout_via_get(self):
        """Logout endpoint supports GET request for user convenience."""
        self.client.login(username='testuser', password='SecurePassword123!')
        url = reverse('logout')
        response = self.client.get(url, follow=True)

        self.assertRedirects(response, reverse('login'))
        self.assertFalse(response.context['user'].is_authenticated)

    def test_authenticated_user_redirected_from_auth_pages(self):
        """Authenticated users visiting login or register are redirected to home."""
        self.client.login(username='testuser', password='SecurePassword123!')

        login_res = self.client.get(reverse('login'))
        self.assertRedirects(login_res, reverse('home'))

        register_res = self.client.get(reverse('register'))
        self.assertRedirects(register_res, reverse('home'))

    def test_unauthenticated_protected_route_redirects_to_login(self):
        """Unauthenticated access to protected routes redirects to login with ?next parameter."""
        dashboard_url = reverse('dashboard')
        response = self.client.get(dashboard_url)
        expected_redirect = f"{reverse('login')}?next={dashboard_url}"
        self.assertRedirects(response, expected_redirect)

    def test_navbar_rendering_authenticated_vs_guest(self):
        """Navbar displays appropriate links based on authentication state."""
        # Guest state
        guest_res = self.client.get(reverse('home'))
        self.assertContains(guest_res, 'Sign In')
        self.assertContains(guest_res, 'Create Account')
        self.assertNotContains(guest_res, 'Sign Out')
        self.assertNotContains(guest_res, 'testuser')

        # Authenticated state
        self.client.login(username='testuser', password='SecurePassword123!')
        auth_res = self.client.get(reverse('home'))
        self.assertContains(auth_res, 'Sign Out')
        self.assertContains(auth_res, 'testuser')
        self.assertContains(auth_res, 'Dashboard')
        self.assertNotContains(auth_res, 'nav-login')

    def test_registration_case_insensitive_duplicate_email(self):
        """Registration fails if email matches an existing email with different casing."""
        url = reverse('register')
        data = {
            'username': 'caseuser',
            'email': 'TESTUSER@EXAMPLE.COM',  # Existing email is testuser@example.com
            'password1': 'StrongPassword789!',
            'password2': 'StrongPassword789!',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'email', 'An account with this email address already exists.')
        self.assertFalse(User.objects.filter(username='caseuser').exists())

    def test_registration_email_whitespace_trimming_and_normalization(self):
        """Registration trims surrounding whitespace and normalizes email address."""
        url = reverse('register')
        data = {
            'username': 'trimmeduser',
            'email': '  TrimmedMember@example.com  ',
            'first_name': 'Trimmed',
            'last_name': 'Member',
            'password1': 'StrongPassword789!',
            'password2': 'StrongPassword789!',
        }
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, reverse('login'))
        self.assertTrue(User.objects.filter(username='trimmeduser').exists())
        user = User.objects.get(username='trimmeduser')
        self.assertEqual(user.email, 'trimmedmember@example.com')

    def test_registration_mandatory_email(self):
        """Registration fails if email is blank because email is required."""
        url = reverse('register')
        data = {
            'username': 'noemailuser',
            'email': '',
            'password1': 'StrongPassword789!',
            'password2': 'StrongPassword789!',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'email', 'This field is required.')
        self.assertFalse(User.objects.filter(username='noemailuser').exists())

    def test_registration_password_validators_enforcement(self):
        """Registration fails when password violates Django password validators."""
        url = reverse('register')
        # Too short (< 8 chars)
        short_data = {
            'username': 'shortpassuser',
            'email': 'short@example.com',
            'password1': '123',
            'password2': '123',
        }
        short_res = self.client.post(url, short_data)
        self.assertEqual(short_res.status_code, 200)
        self.assertIn('password2', short_res.context['form'].errors)
        self.assertTrue(any('too short' in err for err in short_res.context['form'].errors['password2']))
        self.assertFalse(User.objects.filter(username='shortpassuser').exists())

        # Entirely numeric
        numeric_data = {
            'username': 'numericpassuser',
            'email': 'numeric@example.com',
            'password1': '1234567890',
            'password2': '1234567890',
        }
        num_res = self.client.post(url, numeric_data)
        self.assertEqual(num_res.status_code, 200)
        self.assertIn('password2', num_res.context['form'].errors)
        self.assertTrue(any('entirely numeric' in err for err in num_res.context['form'].errors['password2']))
        self.assertFalse(User.objects.filter(username='numericpassuser').exists())

    def test_login_redirect_to_next_parameter(self):
        """Successful login redirects to the specified ?next= parameter rather than home."""
        url = reverse('login') + '?next=' + reverse('dashboard')
        response = self.client.post(url, {
            'username': 'testuser',
            'password': 'SecurePassword123!',
        }, follow=True)
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(response.context['user'].is_authenticated)

    def test_authenticated_users_cannot_submit_registration(self):
        """Already authenticated users submitting POST to registration are redirected to home."""
        self.client.login(username='testuser', password='SecurePassword123!')
        url = reverse('register')
        data = {
            'username': 'thirduser',
            'email': 'thirduser@example.com',
            'password1': 'StrongPassword789!',
            'password2': 'StrongPassword789!',
        }
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse('home'))
        self.assertFalse(User.objects.filter(username='thirduser').exists())

    def test_guest_logout_works_cleanly(self):
        """Guest calling logout redirects to login cleanly without queued messages."""
        url = reverse('logout')

        # Test POST
        post_response = self.client.post(url, follow=True)
        self.assertRedirects(post_response, reverse('login'))
        post_messages = list(get_messages(post_response.wsgi_request))
        self.assertFalse(any('logged out' in str(m).lower() for m in post_messages))

        # Test GET
        get_response = self.client.get(url, follow=True)
        self.assertRedirects(get_response, reverse('login'))
        get_messages_list = list(get_messages(get_response.wsgi_request))
        self.assertFalse(any('logged out' in str(m).lower() for m in get_messages_list))

    def test_authenticated_users_can_access_protected_dashboard(self):
        """Authenticated users can access the protected dashboard route."""
        self.client.login(username='testuser', password='SecurePassword123!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chores/dashboard.html')
        self.assertContains(response, 'Chore Dashboard')
