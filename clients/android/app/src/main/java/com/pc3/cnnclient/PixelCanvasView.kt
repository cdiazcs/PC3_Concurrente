package com.pc3.cnnclient

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import kotlin.math.min

class PixelCanvasView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val gridSize = 16
    private val grid = FloatArray(gridSize * gridSize) { 0f }

    private val activePaint = Paint().apply { style = Paint.Style.FILL }
    private val borderPaint = Paint().apply {
        color = Color.DKGRAY
        style = Paint.Style.STROKE
        strokeWidth = 1f
    }

    var invertColors: Boolean = false
        set(value) {
            field = value
            invalidate()
        }

    fun clear() {
        grid.fill(0f)
        invalidate()
    }

    fun loadFromBitmap(source: Bitmap) {
        val scaled = Bitmap.createScaledBitmap(source, gridSize, gridSize, true)
        for (y in 0 until gridSize) {
            for (x in 0 until gridSize) {
                val px = scaled.getPixel(x, y)
                val r = Color.red(px)
                val g = Color.green(px)
                val b = Color.blue(px)
                val lum = (0.299f * r + 0.587f * g + 0.114f * b) / 255f
                grid[y * gridSize + x] = lum.coerceIn(0f, 1f)
            }
        }
        invalidate()
    }

    fun exportNormalizedVector(): FloatArray {
        return FloatArray(grid.size) { idx ->
            val v = grid[idx]
            if (invertColors) 1f - v else v
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_DOWN || event.action == MotionEvent.ACTION_MOVE) {
            val side = min(width, height).toFloat()
            if (side <= 0f) return true
            val cellSize = side / gridSize
            val gx = (event.x / cellSize).toInt()
            val gy = (event.y / cellSize).toInt()
            if (gx in 0 until gridSize && gy in 0 until gridSize) {
                paintBrush(gx, gy)
                invalidate()
            }
            return true
        }
        return super.onTouchEvent(event)
    }

    private fun paintBrush(cx: Int, cy: Int) {
        grid[cy * gridSize + cx] = 1f
        val neighbors = listOf(-1 to 0, 1 to 0, 0 to -1, 0 to 1)
        for ((dx, dy) in neighbors) {
            val nx = cx + dx
            val ny = cy + dy
            if (nx in 0 until gridSize && ny in 0 until gridSize) {
                grid[ny * gridSize + nx] = maxOf(grid[ny * gridSize + nx], 0.45f)
            }
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val side = min(width, height).toFloat()
        val cellSize = side / gridSize
        for (y in 0 until gridSize) {
            for (x in 0 until gridSize) {
                val raw = grid[y * gridSize + x]
                val v = if (invertColors) 1f - raw else raw
                val intensity = (v * 255).toInt().coerceIn(0, 255)
                activePaint.color = Color.rgb(intensity, intensity, intensity)
                val left = x * cellSize
                val top = y * cellSize
                canvas.drawRect(left, top, left + cellSize, top + cellSize, activePaint)
                canvas.drawRect(left, top, left + cellSize, top + cellSize, borderPaint)
            }
        }
    }
}
