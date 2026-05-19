package org.freesat.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.freesat.ui.theme.*

/**
 * Real-time payload byte counter for message composer.
 *
 * Shows remaining bytes and color-transitions as the user approaches
 * the LoRa frame payload limit (59 bytes after header + FEC + CRC).
 *
 * Visual:
 *   [████████████░░░░░] 42 / 59 bytes
 */
@Composable
fun ByteCounter(
    text: String,
    maxBytes: Int = 59,  // LoRa frame: 80 - 21 header = 59 payload bytes
    modifier: Modifier = Modifier
) {
    val byteCount = text.toByteArray(Charsets.UTF_8).size
    val ratio = (byteCount.toFloat() / maxBytes).coerceIn(0f, 1f)
    val remaining = maxBytes - byteCount
    val overLimit = byteCount > maxBytes

    val barColor by animateColorAsState(
        targetValue = when {
            overLimit -> AlertRed
            ratio > 0.85f -> WarningAmber
            ratio > 0.6f -> SatelliteBlue
            else -> SuccessGreen
        },
        animationSpec = tween(300),
        label = "barColor"
    )

    Column(modifier = modifier.fillMaxWidth()) {
        // Progress bar
        LinearProgressIndicator(
            progress = { ratio },
            modifier = Modifier
                .fillMaxWidth()
                .height(4.dp)
                .clip(RoundedCornerShape(2.dp)),
            color = barColor,
            trackColor = barColor.copy(alpha = 0.15f)
        )

        Spacer(Modifier.height(4.dp))

        // Byte count text
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = if (overLimit) {
                    "⚠ ${-remaining} bytes over limit"
                } else {
                    "$byteCount / $maxBytes bytes"
                },
                fontSize = 11.sp,
                color = barColor,
                fontWeight = if (overLimit) FontWeight.Bold else FontWeight.Normal
            )

            if (!overLimit && byteCount > 0) {
                Text(
                    text = "${remaining} remaining",
                    fontSize = 11.sp,
                    color = TextSecondary
                )
            }
        }
    }
}

/**
 * Compact inline byte counter (for tight spaces).
 * Shows just the count with color coding.
 */
@Composable
fun InlineByteCounter(
    text: String,
    maxBytes: Int = 59,
    modifier: Modifier = Modifier
) {
    val byteCount = text.toByteArray(Charsets.UTF_8).size
    val overLimit = byteCount > maxBytes
    val ratio = byteCount.toFloat() / maxBytes

    val color by animateColorAsState(
        targetValue = when {
            overLimit -> AlertRed
            ratio > 0.85f -> WarningAmber
            else -> TextSecondary
        },
        animationSpec = tween(300),
        label = "inlineColor"
    )

    Text(
        text = "$byteCount/$maxBytes",
        fontSize = 10.sp,
        color = color,
        fontWeight = if (overLimit) FontWeight.Bold else FontWeight.Normal,
        modifier = modifier
    )
}
