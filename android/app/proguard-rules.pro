# ── OpenOrbitLink ProGuard Rules ─────────────────────────────────

# Keep Retrofit interfaces (used via reflection)
-keep,allowobfuscation interface org.freesat.api.OpenOrbitLinkApi
-keepclassmembers interface org.freesat.api.OpenOrbitLinkApi { *; }

# Keep API model classes (Gson serialization)
-keep class org.freesat.api.** { *; }
-keepclassmembers class org.freesat.api.** { *; }

# Keep Room entities and DAOs
-keep class org.freesat.data.** { *; }
-keepclassmembers class org.freesat.data.** { *; }

# Gson — keep @SerializedName annotations
-keepattributes Signature
-keepattributes *Annotation*
-keep class com.google.gson.** { *; }
-keep class * implements com.google.gson.TypeAdapterFactory
-keep class * implements com.google.gson.JsonSerializer
-keep class * implements com.google.gson.JsonDeserializer
-keepclassmembers,allowobfuscation class * {
    @com.google.gson.annotations.SerializedName <fields>;
}

# Retrofit
-dontwarn retrofit2.**
-keep class retrofit2.** { *; }
-keepattributes Exceptions

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class okhttp3.** { *; }

# JNI — keep native methods
-keepclasseswithmembernames class * {
    native <methods>;
}

# Keep Codec2 JNI bridge
-keep class org.freesat.codec.** { *; }
-keep class org.freesat.hal.** { *; }

# Coroutines
-dontwarn kotlinx.coroutines.**

# Room
-keep class * extends androidx.room.RoomDatabase
-dontwarn androidx.room.paging.**
