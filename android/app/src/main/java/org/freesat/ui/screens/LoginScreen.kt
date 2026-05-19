package org.freesat.ui.screens

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.freesat.auth.ApiClient
import org.freesat.auth.AuthTokenManager
import org.freesat.api.ApiClient as OolApiClient
import org.freesat.ui.theme.*

/**
 * OpenOrbitLink Login Screen — Auth gate before any RF/DTN functionality.
 *
 * Features:
 * - Login / Register toggle
 * - Invite code field (required for registration)
 * - Orbital animation during loading
 * - Space Dark theme consistent with the rest of the app
 * - Keystore-backed token storage on success
 */
@Composable
fun LoginScreen(onLoginSuccess: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val focusManager = LocalFocusManager.current
    val snackbarHostState = remember { SnackbarHostState() }

    val authManager = remember { AuthTokenManager(context) }
    val apiClient = remember { ApiClient(tokenManager = authManager) }

    var isRegisterMode by remember { mutableStateOf(false) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var inviteCode by remember { mutableStateOf("") }
    var showPassword by remember { mutableStateOf(false) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    // Server URL config
    var showServerConfig by remember { mutableStateOf(false) }
    var serverUrl by remember { mutableStateOf(OolApiClient.getBaseUrl(context)) }
    var serverTestResult by remember { mutableStateOf<Boolean?>(null) }
    var serverTesting by remember { mutableStateOf(false) }

    // Orbital animation
    val infiniteTransition = rememberInfiniteTransition(label = "orbit")
    val orbitAngle by infiniteTransition.animateFloat(
        0f, 360f,
        infiniteRepeatable(tween(8000, easing = LinearEasing)),
        label = "angle"
    )
    val pulseAlpha by infiniteTransition.animateFloat(
        0.3f, 0.8f,
        infiniteRepeatable(tween(2000), RepeatMode.Reverse),
        label = "pulse"
    )

    fun submit() {
        if (username.isBlank() || password.isBlank()) {
            errorMessage = "Username and password are required"
            return
        }
        if (isRegisterMode && inviteCode.isBlank()) {
            errorMessage = "Invite code required for registration"
            return
        }
        if (password.length < 8) {
            errorMessage = "Password must be at least 8 characters"
            return
        }

        isLoading = true
        errorMessage = null

        scope.launch {
            val result = if (isRegisterMode) {
                apiClient.register(username, password, inviteCode, email.ifBlank { null })
            } else {
                apiClient.login(username, password)
            }

            isLoading = false

            if (result.success) {
                authManager.saveToken(result.token, result.username, result.userId, result.expiresInHours)
                snackbarHostState.showSnackbar("Welcome, ${result.username}!")
                onLoginSuccess()
            } else {
                errorMessage = result.error
            }
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        containerColor = Color.Transparent
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy, SpaceBlack)))
                .padding(padding)
                .verticalScroll(rememberScrollState()),
            contentAlignment = Alignment.Center
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 32.dp, vertical = 48.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                // ── Logo / Orbital Animation ──
                Box(contentAlignment = Alignment.Center, modifier = Modifier.padding(bottom = 32.dp)) {
                    // Outer orbit ring
                    Box(
                        modifier = Modifier
                            .size(120.dp)
                            .clip(CircleShape)
                            .background(SatelliteBlue.copy(alpha = 0.06f))
                            .border(
                                BorderStroke(1.dp, SatelliteBlue.copy(alpha = pulseAlpha * 0.3f)),
                                CircleShape
                            )
                    )
                    // Inner ring
                    Box(
                        modifier = Modifier
                            .size(80.dp)
                            .clip(CircleShape)
                            .background(
                                Brush.radialGradient(
                                    listOf(AccentGradientStart.copy(alpha = 0.2f), Color.Transparent)
                                )
                            )
                    )
                    // Orbiting dot
                    Box(
                        modifier = Modifier
                            .size(120.dp)
                            .rotate(orbitAngle)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(10.dp)
                                .align(Alignment.TopCenter)
                                .clip(CircleShape)
                                .background(SatelliteBlue)
                        )
                    }
                    // Center icon
                    Icon(
                        Icons.Filled.SatelliteAlt, null,
                        tint = SatelliteBlue,
                        modifier = Modifier.size(36.dp)
                    )
                }

                // ── Title ──
                Text(
                    "OpenOrbitLink",
                    style = MaterialTheme.typography.headlineLarge,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary
                )
                Text(
                    "Delay-Tolerant Satellite Messaging",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = WarningAmber.copy(alpha = 0.1f),
                    border = BorderStroke(1.dp, WarningAmber.copy(alpha = 0.3f)),
                    modifier = Modifier.padding(bottom = 32.dp)
                ) {
                    Text(
                        "Closed Beta • Invite Only",
                        color = WarningAmber,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp)
                    )
                }

                // ── Mode Toggle ──
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 20.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    FilterChip(
                        selected = !isRegisterMode,
                        onClick = { isRegisterMode = false; errorMessage = null },
                        label = { Text("Login") },
                        leadingIcon = { Icon(Icons.Filled.Login, null, Modifier.size(16.dp)) },
                        modifier = Modifier.weight(1f),
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = SatelliteBlue.copy(alpha = 0.18f)
                        )
                    )
                    FilterChip(
                        selected = isRegisterMode,
                        onClick = { isRegisterMode = true; errorMessage = null },
                        label = { Text("Register") },
                        leadingIcon = { Icon(Icons.Filled.PersonAdd, null, Modifier.size(16.dp)) },
                        modifier = Modifier.weight(1f),
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = AccentGradientStart.copy(alpha = 0.18f)
                        )
                    )
                }

                // ── Form ──
                GlassCard(modifier = Modifier.fillMaxWidth()) {
                    // Username
                    OutlinedTextField(
                        value = username, onValueChange = { username = it },
                        label = { Text("Username") },
                        leadingIcon = { Icon(Icons.Outlined.Person, null) },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                        keyboardActions = KeyboardActions(onNext = { focusManager.moveFocus(FocusDirection.Down) }),
                        modifier = Modifier.fillMaxWidth(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = SatelliteBlue,
                            unfocusedBorderColor = Color.White.copy(alpha = 0.1f),
                            cursorColor = SatelliteBlue,
                            focusedLabelColor = SatelliteBlue
                        )
                    )

                    Spacer(Modifier.height(12.dp))

                    // Email (register only)
                    if (isRegisterMode) {
                        OutlinedTextField(
                            value = email, onValueChange = { email = it },
                            label = { Text("Email (optional)") },
                            leadingIcon = { Icon(Icons.Outlined.Email, null) },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
                            keyboardActions = KeyboardActions(onNext = { focusManager.moveFocus(FocusDirection.Down) }),
                            modifier = Modifier.fillMaxWidth(),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = SatelliteBlue,
                                unfocusedBorderColor = Color.White.copy(alpha = 0.1f),
                                cursorColor = SatelliteBlue,
                                focusedLabelColor = SatelliteBlue
                            )
                        )
                        Spacer(Modifier.height(12.dp))
                    }

                    // Password
                    OutlinedTextField(
                        value = password, onValueChange = { password = it },
                        label = { Text("Password") },
                        leadingIcon = { Icon(Icons.Outlined.Lock, null) },
                        trailingIcon = {
                            IconButton(onClick = { showPassword = !showPassword }) {
                                Icon(
                                    if (showPassword) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                                    null, tint = TextSecondary
                                )
                            }
                        },
                        singleLine = true,
                        visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = if (isRegisterMode) ImeAction.Next else ImeAction.Done),
                        keyboardActions = KeyboardActions(
                            onNext = { focusManager.moveFocus(FocusDirection.Down) },
                            onDone = { submit() }
                        ),
                        modifier = Modifier.fillMaxWidth(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = SatelliteBlue,
                            unfocusedBorderColor = Color.White.copy(alpha = 0.1f),
                            cursorColor = SatelliteBlue,
                            focusedLabelColor = SatelliteBlue
                        )
                    )

                    // Invite code (register only)
                    if (isRegisterMode) {
                        Spacer(Modifier.height(12.dp))
                        OutlinedTextField(
                            value = inviteCode, onValueChange = { inviteCode = it.uppercase() },
                            label = { Text("Invite Code") },
                            leadingIcon = { Icon(Icons.Outlined.Key, null) },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                            keyboardActions = KeyboardActions(onDone = { submit() }),
                            modifier = Modifier.fillMaxWidth(),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = AccentGradientStart,
                                unfocusedBorderColor = Color.White.copy(alpha = 0.1f),
                                cursorColor = AccentGradientStart,
                                focusedLabelColor = AccentGradientStart
                            )
                        )
                    }

                    // Error message
                    errorMessage?.let { err ->
                        Spacer(Modifier.height(12.dp))
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = AlertRed.copy(alpha = 0.1f)
                        ) {
                            Row(
                                modifier = Modifier.padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(Icons.Filled.ErrorOutline, null, tint = AlertRed, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(8.dp))
                                Text(err, color = AlertRed, fontSize = 13.sp)
                            }
                        }
                    }

                    Spacer(Modifier.height(20.dp))

                    // Submit button
                    Button(
                        onClick = { submit() },
                        enabled = !isLoading,
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                        shape = RoundedCornerShape(16.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = SatelliteBlue,
                            contentColor = SpaceBlack
                        )
                    ) {
                        if (isLoading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(22.dp),
                                color = SpaceBlack,
                                strokeWidth = 2.dp
                            )
                            Spacer(Modifier.width(10.dp))
                            Text("Connecting to ground station...")
                        } else {
                            Icon(
                                if (isRegisterMode) Icons.Filled.PersonAdd else Icons.Filled.Login,
                                null, modifier = Modifier.size(20.dp)
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                if (isRegisterMode) "Create Account" else "Sign In",
                                fontWeight = FontWeight.Bold, fontSize = 16.sp
                            )
                        }
                    }
                }

                // ── Server URL Config ──
                Spacer(Modifier.height(16.dp))
                Surface(
                    onClick = { showServerConfig = !showServerConfig },
                    shape = RoundedCornerShape(12.dp),
                    color = Color.Transparent
                ) {
                    Row(
                        modifier = Modifier.padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Filled.Settings, null, tint = TextSecondary, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Server: ${serverUrl.take(30)}", color = TextSecondary, fontSize = 11.sp)
                        Spacer(Modifier.width(4.dp))
                        Icon(
                            if (showServerConfig) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                            null, tint = TextSecondary, modifier = Modifier.size(16.dp)
                        )
                    }
                }

                if (showServerConfig) {
                    Spacer(Modifier.height(8.dp))
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        Text("Backend Server", fontWeight = FontWeight.Bold, color = SatelliteBlue, fontSize = 14.sp)
                        Text("Enter the IP/URL of your FastAPI backend", color = TextSecondary, fontSize = 11.sp)
                        Spacer(Modifier.height(10.dp))
                        OutlinedTextField(
                            value = serverUrl, onValueChange = { serverUrl = it; serverTestResult = null },
                            label = { Text("Server URL") },
                            placeholder = { Text("http://192.168.1.100:8000") },
                            leadingIcon = { Icon(Icons.Filled.Dns, null) },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = SatelliteBlue,
                                unfocusedBorderColor = Color.White.copy(alpha = 0.1f),
                                cursorColor = SatelliteBlue,
                                focusedLabelColor = SatelliteBlue
                            )
                        )
                        Spacer(Modifier.height(10.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            // Test connection
                            OutlinedButton(
                                onClick = {
                                    serverTesting = true
                                    serverTestResult = null
                                    scope.launch {
                                        serverTestResult = OolApiClient.testConnection(serverUrl)
                                        serverTesting = false
                                        if (serverTestResult == true) {
                                            OolApiClient.setBaseUrl(context, serverUrl)
                                        }
                                    }
                                },
                                enabled = !serverTesting && serverUrl.isNotBlank(),
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(12.dp)
                            ) {
                                if (serverTesting) {
                                    CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                                } else {
                                    Icon(Icons.Filled.NetworkCheck, null, modifier = Modifier.size(16.dp))
                                }
                                Spacer(Modifier.width(6.dp))
                                Text("Test Connection")
                            }
                            // Save
                            Button(
                                onClick = {
                                    OolApiClient.setBaseUrl(context, serverUrl)
                                    showServerConfig = false
                                },
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(12.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = SuccessGreen)
                            ) {
                                Icon(Icons.Filled.Save, null, modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Save", color = SpaceBlack)
                            }
                        }
                        // Test result
                        serverTestResult?.let { ok ->
                            Spacer(Modifier.height(8.dp))
                            Surface(
                                shape = RoundedCornerShape(8.dp),
                                color = (if (ok) SuccessGreen else AlertRed).copy(alpha = 0.1f)
                            ) {
                                Row(modifier = Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Icon(
                                        if (ok) Icons.Filled.CheckCircle else Icons.Filled.ErrorOutline,
                                        null, tint = if (ok) SuccessGreen else AlertRed, modifier = Modifier.size(16.dp)
                                    )
                                    Spacer(Modifier.width(8.dp))
                                    Text(
                                        if (ok) "Connected! Backend is healthy." else "Cannot reach server. Check URL and ensure backend is running.",
                                        color = if (ok) SuccessGreen else AlertRed, fontSize = 12.sp
                                    )
                                }
                            }
                        }
                    }
                }

                // ── Footer info ──
                Spacer(Modifier.height(16.dp))
                Text(
                    "Token stored in Android Keystore\nEnd-to-end encrypted • ISM 868 MHz",
                    color = TextSecondary,
                    fontSize = 11.sp,
                    textAlign = TextAlign.Center,
                    lineHeight = 16.sp
                )
            }
        }
    }
}
