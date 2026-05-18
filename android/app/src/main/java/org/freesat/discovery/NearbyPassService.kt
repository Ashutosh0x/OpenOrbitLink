package org.freesat.discovery

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Binder
import android.os.IBinder
import org.freesat.MainActivity
import org.freesat.R

class NearbyPassService : Service() {
    private val binder = LocalBinder()

    inner class LocalBinder : Binder() {
        fun service(): NearbyPassService = this@NearbyPassService
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification("Scoring nearby satellite passes"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val best = latestCandidates().maxBy { NearbyPassScorer.score(it) }
        startForeground(NOTIFICATION_ID, buildNotification("${best.name}: ${NearbyPassScorer.recommendation(best)}"))
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder = binder

    fun latestCandidates(): List<NearbyPassCandidate> = NearbyPassScorer.demoCandidates()

    private fun buildNotification(text: String): Notification {
        val contentIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle("OpenOrbitLink nearby passes")
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(contentIntent)
            .build()
    }

    private fun createNotificationChannel() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Nearby satellite discovery",
            NotificationManager.IMPORTANCE_LOW,
        )
        manager.createNotificationChannel(channel)
    }

    companion object {
        const val CHANNEL_ID = "openorbitlink_nearby_passes"
        const val NOTIFICATION_ID = 3107
    }
}
