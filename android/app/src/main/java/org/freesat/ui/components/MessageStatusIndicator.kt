package org.freesat.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Three-state message delivery status indicator.
 *
 * States:
 *   QUEUED      -> Gray clock icon, "Queued"
 *   TRANSMITTED -> Yellow radio icon, "Transmitted"
 *   DELIVERED   -> Green check icon, "Delivered"
 *
 * Includes animated transitions between states.
 */

enum class MessageDeliveryState {
    QUEUED,
    TRANSMITTED,
    DELIVERED,
}

@Composable
fun MessageStatusIndicator(
    state: MessageDeliveryState,
    compact: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val targetColor = when (state) {
        MessageDeliveryState.QUEUED -> Color(0xFF8B949E)
        MessageDeliveryState.TRANSMITTED -> Color(0xFFFFA726)
        MessageDeliveryState.DELIVERED -> Color(0xFF66BB6A)
    }

    val animatedColor by animateColorAsState(
        targetValue = targetColor,
        animationSpec = tween(500),
        label = "statusColor",
    )

    val icon = when (state) {
        MessageDeliveryState.QUEUED -> Icons.Default.Schedule
        MessageDeliveryState.TRANSMITTED -> Icons.Default.CellTower
        MessageDeliveryState.DELIVERED -> Icons.Default.CheckCircle
    }

    val label = when (state) {
        MessageDeliveryState.QUEUED -> "Queued"
        MessageDeliveryState.TRANSMITTED -> "Transmitted"
        MessageDeliveryState.DELIVERED -> "Delivered"
    }

    // Pulse animation for TRANSMITTED state
    val pulseScale = if (state == MessageDeliveryState.TRANSMITTED) {
        val transition = rememberInfiniteTransition(label = "pulse")
        val scale by transition.animateFloat(
            initialValue = 1f,
            targetValue = 1.15f,
            animationSpec = infiniteRepeatable(
                animation = tween(800, easing = EaseInOutSine),
                repeatMode = RepeatMode.Reverse,
            ),
            label = "pulseScale",
        )
        scale
    } else {
        1f
    }

    if (compact) {
        // Compact: just icon with tooltip
        Icon(
            imageVector = icon,
            contentDescription = label,
            tint = animatedColor,
            modifier = modifier
                .size(20.dp)
                .scale(pulseScale),
        )
    } else {
        // Full: icon + label in chip
        Surface(
            modifier = modifier,
            shape = RoundedCornerShape(16.dp),
            color = animatedColor.copy(alpha = 0.12f),
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = animatedColor,
                    modifier = Modifier
                        .size(16.dp)
                        .scale(pulseScale),
                )
                Text(
                    text = label,
                    color = animatedColor,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                )
            }
        }
    }
}

/**
 * Message status timeline showing all three states.
 *
 * Renders a horizontal timeline with dots and connecting lines:
 *   [Queued] ---- [Transmitted] ---- [Delivered]
 */
@Composable
fun MessageStatusTimeline(
    currentState: MessageDeliveryState,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val states = MessageDeliveryState.entries

        states.forEachIndexed { index, state ->
            val isActive = state.ordinal <= currentState.ordinal
            val color = if (isActive) {
                when (state) {
                    MessageDeliveryState.QUEUED -> Color(0xFF8B949E)
                    MessageDeliveryState.TRANSMITTED -> Color(0xFFFFA726)
                    MessageDeliveryState.DELIVERED -> Color(0xFF66BB6A)
                }
            } else {
                Color(0xFF30363D)
            }

            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.weight(1f),
            ) {
                Box(
                    modifier = Modifier
                        .size(if (isActive) 12.dp else 8.dp)
                        .clip(CircleShape)
                        .background(color),
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = state.name.lowercase().replaceFirstChar { it.uppercase() },
                    color = color,
                    fontSize = 10.sp,
                    fontWeight = if (isActive) FontWeight.Medium else FontWeight.Normal,
                )
            }

            if (index < states.size - 1) {
                Box(
                    modifier = Modifier
                        .weight(0.5f)
                        .height(2.dp)
                        .background(
                            if (states[index + 1].ordinal <= currentState.ordinal) {
                                Color(0xFF4FC3F7)
                            } else {
                                Color(0xFF30363D)
                            }
                        ),
                )
            }
        }
    }
}
