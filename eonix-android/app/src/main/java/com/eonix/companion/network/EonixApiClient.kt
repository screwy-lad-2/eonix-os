package com.eonix.companion.network

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.eonix.companion.data.ContextResponse
import com.eonix.companion.data.GoalResponse
import com.eonix.companion.data.MemoryItem
import com.eonix.companion.data.SyncStateResponse
import com.eonix.companion.data.SyncStatusResponse
import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume

private const val TAG = "EonixAPI"

class EonixDiscovery(private val context: Context) {
    private val prefs = context.getSharedPreferences("eonix_companion", Context.MODE_PRIVATE)

    suspend fun discoverDesktop(): String? {
        val nsdManager = context.getSystemService(Context.NSD_SERVICE) as? NsdManager
            ?: return fallbackIp()

        return suspendCancellableCoroutine { cont ->
            var resolved = false
            lateinit var discoveryListener: NsdManager.DiscoveryListener

            val timeoutHandler = Handler(Looper.getMainLooper())
            val timeoutRunnable = Runnable {
                if (!resolved && cont.isActive) {
                    resolved = true
                    runCatching { nsdManager.stopServiceDiscovery(discoveryListener) }
                    cont.resume(fallbackIp())
                }
            }

            discoveryListener = object : NsdManager.DiscoveryListener {
                override fun onDiscoveryStarted(serviceType: String) = Unit

                override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                    if (resolved || serviceInfo.serviceType != "_eonix._tcp.") return
                    nsdManager.resolveService(serviceInfo, object : NsdManager.ResolveListener {
                        override fun onServiceResolved(info: NsdServiceInfo) {
                            if (resolved) return
                            resolved = true
                            timeoutHandler.removeCallbacks(timeoutRunnable)
                            val ip = info.host?.hostAddress
                            if (!ip.isNullOrBlank()) {
                                prefs.edit().putString("eonix_desktop_ip", ip).apply()
                                cont.resume(ip)
                            } else {
                                cont.resume(fallbackIp())
                            }
                            runCatching { nsdManager.stopServiceDiscovery(discoveryListener) }
                        }

                        override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) = Unit
                    })
                }

                override fun onServiceLost(serviceInfo: NsdServiceInfo) = Unit
                override fun onDiscoveryStopped(serviceType: String) = Unit

                override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                    if (!resolved && cont.isActive) {
                        resolved = true
                        timeoutHandler.removeCallbacks(timeoutRunnable)
                        cont.resume(fallbackIp())
                    }
                }

                override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
                    if (!resolved && cont.isActive) {
                        resolved = true
                        timeoutHandler.removeCallbacks(timeoutRunnable)
                        cont.resume(fallbackIp())
                    }
                }
            }

            nsdManager.discoverServices("_eonix._tcp.", NsdManager.PROTOCOL_DNS_SD, discoveryListener)
            timeoutHandler.postDelayed(timeoutRunnable, 10_000)
            cont.invokeOnCancellation {
                timeoutHandler.removeCallbacks(timeoutRunnable)
                runCatching { nsdManager.stopServiceDiscovery(discoveryListener) }
            }
        }
    }

    private fun fallbackIp(): String? = prefs.getString("eonix_desktop_ip", null)
}

private interface EonixApi {
    @GET("goal/active")
    suspend fun getActiveGoal(): Response<GoalResponse>

    @GET("goal/progress/{goalId}")
    suspend fun getGoalProgress(@Path("goalId") goalId: String): Response<Map<String, Any>>

    @POST("goal/create")
    suspend fun createGoal(@Body body: Map<String, String>): Response<Map<String, Any>>

    @GET("context/summary")
    suspend fun getContextSummary(@Query("hours") hours: Int = 2): Response<ContextResponse>

    @GET("sync/state")
    suspend fun getSyncState(): Response<SyncStateResponse>

    @GET("sync/status")
    suspend fun getSyncStatus(): Response<SyncStatusResponse>

    @POST("sync/voice")
    suspend fun sendVoice(@Body payload: Map<String, String>): Response<Map<String, Any>>

    @POST("sync/push")
    suspend fun pushSync(@Body payload: Map<String, String>): Response<Map<String, Any>>
}

class EonixApiClient(private val context: Context) {
    private val discovery = EonixDiscovery(context)

    private fun createRetrofit(ip: String, port: Int): Retrofit {
        val logger = HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC }
        val client = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .addInterceptor(logger)
            .build()

        return Retrofit.Builder()
            .baseUrl("http://$ip:$port/")
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }

    private suspend fun resolveIp(): String? = try {
        discovery.discoverDesktop()
    } catch (e: Exception) {
        Log.e(TAG, "Discovery failed", e)
        null
    }

    suspend fun getActiveGoal(): GoalResponse? {
        val ip = resolveIp() ?: return null
        return runCatching {
            createRetrofit(ip, 7735).create(EonixApi::class.java).getActiveGoal().body()
        }.onFailure { Log.e(TAG, "getActiveGoal failed", it) }.getOrNull()
    }

    suspend fun getGoalProgress(goalId: String): Float {
        val ip = resolveIp() ?: return 0f
        return runCatching {
            val body = createRetrofit(ip, 7735).create(EonixApi::class.java).getGoalProgress(goalId).body()
            (body?.get("progress") as? Number)?.toFloat() ?: 0f
        }.onFailure { Log.e(TAG, "getGoalProgress failed", it) }.getOrDefault(0f)
    }

    suspend fun getContextSummary(): ContextResponse? {
        val ip = resolveIp() ?: return null
        return runCatching {
            createRetrofit(ip, 7736).create(EonixApi::class.java).getContextSummary().body()
        }.onFailure { Log.e(TAG, "getContextSummary failed", it) }.getOrNull()
    }

    suspend fun getMemorySummary(): List<MemoryItem> {
        val ip = resolveIp() ?: return emptyList()
        return runCatching {
            createRetrofit(ip, 7740).create(EonixApi::class.java).getSyncState().body()?.memory_summary ?: emptyList()
        }.onFailure { Log.e(TAG, "getMemorySummary failed", it) }.getOrDefault(emptyList())
    }

    suspend fun getSyncStatus(): SyncStatusResponse? {
        val ip = resolveIp() ?: return null
        return runCatching {
            createRetrofit(ip, 7740).create(EonixApi::class.java).getSyncStatus().body()
        }.onFailure { Log.e(TAG, "getSyncStatus failed", it) }.getOrNull()
    }

    suspend fun sendVoiceCommand(text: String): String {
        val ip = resolveIp() ?: return "Desktop did not respond"
        return runCatching {
            val body = createRetrofit(ip, 7740).create(EonixApi::class.java)
                .sendVoice(mapOf("command" to text, "source" to "android"))
                .body()
            body?.get("reply")?.toString() ?: "Desktop did not respond"
        }.onFailure { Log.e(TAG, "sendVoiceCommand failed", it) }.getOrDefault("Desktop did not respond")
    }

    suspend fun pushGoalFromPhone(name: String, desc: String): Boolean {
        val ip = resolveIp() ?: return false
        return runCatching {
            val body = createRetrofit(ip, 7735).create(EonixApi::class.java)
                .createGoal(mapOf("name" to name, "description" to desc))
                .body()
            body?.get("ok") as? Boolean ?: false
        }.onFailure { Log.e(TAG, "pushGoalFromPhone failed", it) }.getOrDefault(false)
    }

    suspend fun syncNow(): Boolean {
        val ip = resolveIp() ?: return false
        return runCatching {
            val body = createRetrofit(ip, 7740).create(EonixApi::class.java).pushSync(emptyMap()).body()
            body?.get("ok") as? Boolean ?: false
        }.onFailure { Log.e(TAG, "syncNow failed", it) }.getOrDefault(false)
    }

    suspend fun getSystemSnapshot(): Map<String, Float> {
        val ip = resolveIp() ?: return emptyMap()
        return runCatching {
            createRetrofit(ip, 7740).create(EonixApi::class.java).getSyncState().body()?.system_snapshot ?: emptyMap()
        }.onFailure { Log.e(TAG, "getSystemSnapshot failed", it) }.getOrDefault(emptyMap())
    }
}
