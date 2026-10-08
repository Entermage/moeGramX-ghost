package org.thunderdog.challegram.util;

import org.thunderdog.challegram.Log;

import java.io.EOFException;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;

public final class FileCopyUtils {
  private static final long TRANSFER_CHUNK_SIZE = 16L * 1024 * 1024;
  private static final int BUFFER_SIZE = 64 * 1024;

  private FileCopyUtils () { }

  public static boolean copy (File source, File destination) {
    boolean openedDestination = false;
    try {
      if (source.getCanonicalFile().equals(destination.getCanonicalFile())) {
        return false;
      }
      try (FileInputStream input = new FileInputStream(source)) {
        try (FileOutputStream output = new FileOutputStream(destination)) {
          openedDestination = true;
          copyChannels(input.getChannel(), output.getChannel());
          output.flush();
        }
      }
      return true;
    } catch (Throwable t) {
      Log.e("Unable to copy file", t);
      if (openedDestination && !destination.delete()) {
        Log.w("Unable to remove incomplete file copy");
      }
      return false;
    }
  }

  static void copyChannels (FileChannel source, FileChannel destination) throws IOException {
    final long size = source.size();
    long position = 0;
    ByteBuffer buffer = null;
    while (position < size) {
      // transferTo may copy fewer bytes than requested, including zero.
      long copied = source.transferTo(position, Math.min(TRANSFER_CHUNK_SIZE, size - position), destination);
      if (copied > 0) {
        position += copied;
        continue;
      }
      if (buffer == null) {
        buffer = ByteBuffer.allocate(BUFFER_SIZE);
      }
      buffer.clear();
      buffer.limit((int) Math.min(buffer.capacity(), size - position));
      int read = source.read(buffer, position);
      if (read <= 0) {
        throw new EOFException("Source ended before the file copy completed");
      }
      buffer.flip();
      while (buffer.hasRemaining()) {
        if (destination.write(buffer) <= 0) {
          throw new IOException("File copy made no write progress");
        }
      }
      position += read;
    }
    if (source.size() != size || destination.size() != size) {
      throw new IOException("File size changed during the copy");
    }
  }
}
