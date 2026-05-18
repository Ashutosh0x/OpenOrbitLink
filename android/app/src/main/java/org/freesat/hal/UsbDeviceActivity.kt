package org.freesat.hal

import android.app.Activity
import android.os.Bundle
import android.util.Log

class UsbDeviceActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i("OpenOrbitLink", "USB SDR device attached")
        finish()
    }
}
