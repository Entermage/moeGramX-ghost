/*
 * This file is a part of moeGramX.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package moe.kirao.mgx.layout;

/** Direction arbitration shared by the divider and its narrow, non-consuming side margins. */
public final class MoexPaneResizeGesture {
  private static final int IDLE = 0, PENDING = 1, DRAGGING = 2;
  private int state;
  private float startX, startY;

  public void begin (float x, float y) {
    startX = x;
    startY = y;
    state = PENDING;
  }

  public boolean move (float x, float y, float touchSlop) {
    if (state == PENDING) {
      float dx = Math.abs(x - startX), dy = Math.abs(y - startY);
      // A vertical or diagonal start belongs to the content for the rest of this gesture.
      if (dx > touchSlop || dy > touchSlop) {
        state = dx > touchSlop && dx > dy * 1.5f ? DRAGGING : IDLE;
      }
    }
    return state == DRAGGING;
  }

  public boolean isPending () { return state == PENDING; }
  public boolean isDragging () { return state == DRAGGING; }
  public float startX () { return startX; }
  public float startY () { return startY; }
  public float deltaX (float x) { return x - startX; }
  public void cancel () { state = IDLE; }
}
