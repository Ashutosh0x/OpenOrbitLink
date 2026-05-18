package org.freesat.mesh

import android.app.Service
import android.content.Intent
import android.os.IBinder

class MeshRelayService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null
}
