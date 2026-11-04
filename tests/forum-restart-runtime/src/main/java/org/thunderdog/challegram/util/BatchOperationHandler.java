package org.thunderdog.challegram.util;

/** Android Handler double: the batch runs at once. */
public class BatchOperationHandler {
  private final Runnable operation;
  public BatchOperationHandler (Runnable operation, long batchDelay) { this.operation = operation; }
  public void performOperation () { operation.run(); }
}
