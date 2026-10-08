package org.thunderdog.challegram.util;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.ReadableByteChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;

public final class FileCopyUtilsTest {
  private static void check (boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }

  public static void main (String[] args) throws Exception {
    Path dir = Path.of(args[1]);
    File source = dir.resolve("source.bin").toFile();
    File target = dir.resolve("target.bin").toFile();
    byte[] content = new byte[131123];
    for (int i = 0; i < content.length; i++) content[i] = (byte) (i * 31 + i / 257);
    Files.write(source.toPath(), content);
    switch (args[0]) {
      case "overwrite":
        Files.write(target.toPath(), new byte[content.length * 2]);
        check(FileCopyUtils.copy(source, target), "copy must succeed");
        check(Arrays.equals(content, Files.readAllBytes(target.toPath())), "exact bytes and no old tail");
        break;
      case "empty":
        Files.write(source.toPath(), new byte[0]);
        check(FileCopyUtils.copy(source, target), "empty copy must succeed");
        check(target.length() == 0, "empty destination");
        break;
      case "short-transfer":
      case "zero-transfer":
      case "zero-then-short":
      case "early-eof":
      case "stalled-write":
      case "single-transfer-control":
        try (RandomAccessFile input = new RandomAccessFile(source, "r");
             RandomAccessFile output = new RandomAccessFile(target, "rw")) {
          LimitedChannel in = new LimitedChannel(input.getChannel());
          LimitedChannel out = new LimitedChannel(output.getChannel());
          in.limit = 4093;
          in.zeroAlways = args[0].equals("zero-transfer") || args[0].equals("stalled-write");
          in.zeroOnce = args[0].equals("zero-then-short");
          in.extraSize = args[0].equals("early-eof") ? 1 : 0;
          out.stallWrites = args[0].equals("stalled-write");
          out.writeLimit = 101;
          if (args[0].equals("single-transfer-control")) {
            in.transferTo(0, in.size(), out);
            check(target.length() < source.length(), "one transfer must expose incomplete copy");
          } else if (args[0].equals("early-eof") || args[0].equals("stalled-write")) {
            boolean failed = false;
            try { FileCopyUtils.copyChannels(in, out); } catch (IOException expected) { failed = true; }
            check(failed, "incomplete copy must fail without spinning");
          } else {
            FileCopyUtils.copyChannels(in, out);
            check(Arrays.equals(content, Files.readAllBytes(target.toPath())), "all bytes after partial transfer");
          }
        }
        break;
      case "same-file":
        check(!FileCopyUtils.copy(source, source), "same path must be rejected");
        check(Arrays.equals(content, Files.readAllBytes(source.toPath())), "source must survive");
        break;
      case "missing-source":
        Files.write(target.toPath(), content);
        check(!FileCopyUtils.copy(dir.resolve("missing.bin").toFile(), target), "missing source must fail");
        check(Arrays.equals(content, Files.readAllBytes(target.toPath())), "existing destination untouched before open");
        break;
      case "directory-target":
        check(target.mkdir(), "make target directory");
        check(!FileCopyUtils.copy(source, target), "directory destination must fail");
        check(target.isDirectory(), "directory must survive");
        break;
      case "large":
        long size = (1L << 31) + 65537;
        try (RandomAccessFile file = new RandomAccessFile(source, "rw")) {
          file.setLength(size);
          file.seek((1L << 31) - 32);
          file.write(content, 0, 64);
          file.seek(size - 64);
          file.write(content, 64, 64);
        }
        check(FileCopyUtils.copy(source, target), "large copy must succeed");
        check(target.length() == size, "64-bit destination length");
        check(Arrays.equals(hash(source), hash(target)), "large copy full SHA-256");
        System.out.println("large bytes=" + size);
        break;
      default: throw new AssertionError(args[0]);
    }
    System.out.println("PASS " + args[0]);
  }

  private static byte[] hash (File file) throws Exception {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    try (var input = Files.newInputStream(file.toPath())) {
      byte[] buffer = new byte[1024 * 1024];
      int read;
      while ((read = input.read(buffer)) != -1) digest.update(buffer, 0, read);
    }
    return digest.digest();
  }

  private static final class LimitedChannel extends FileChannel {
    final FileChannel delegate;
    long limit = Long.MAX_VALUE;
    long extraSize;
    boolean zeroAlways;
    boolean zeroOnce;
    boolean stallWrites;
    int writeLimit = Integer.MAX_VALUE;
    LimitedChannel (FileChannel delegate) { this.delegate = delegate; }
    @Override public long transferTo (long position, long count, WritableByteChannel target) throws IOException {
      if (zeroAlways) return 0;
      if (zeroOnce) { zeroOnce = false; return 0; }
      return delegate.transferTo(position, Math.min(limit, count), target);
    }
    @Override public int read (ByteBuffer dst, long position) throws IOException { return delegate.read(dst, position); }
    @Override public int read (ByteBuffer dst) throws IOException { return delegate.read(dst); }
    @Override public long read (ByteBuffer[] dsts, int offset, int length) throws IOException { return delegate.read(dsts, offset, length); }
    @Override public int write (ByteBuffer src) throws IOException {
      if (stallWrites) return 0;
      int oldLimit = src.limit();
      src.limit(src.position() + Math.min(writeLimit, src.remaining()));
      try { return delegate.write(src); } finally { src.limit(oldLimit); }
    }
    @Override public int write (ByteBuffer src, long position) throws IOException { return delegate.write(src, position); }
    @Override public long write (ByteBuffer[] srcs, int offset, int length) throws IOException { return delegate.write(srcs, offset, length); }
    @Override public long position () throws IOException { return delegate.position(); }
    @Override public FileChannel position (long value) throws IOException { delegate.position(value); return this; }
    @Override public long size () throws IOException { return delegate.size() + extraSize; }
    @Override public FileChannel truncate (long value) throws IOException { delegate.truncate(value); return this; }
    @Override public void force (boolean metadata) throws IOException { delegate.force(metadata); }
    @Override public long transferFrom (ReadableByteChannel src, long position, long count) throws IOException { return delegate.transferFrom(src, position, count); }
    @Override public MappedByteBuffer map (MapMode mode, long position, long size) throws IOException { return delegate.map(mode, position, size); }
    @Override public FileLock lock (long position, long size, boolean shared) throws IOException { return delegate.lock(position, size, shared); }
    @Override public FileLock tryLock (long position, long size, boolean shared) throws IOException { return delegate.tryLock(position, size, shared); }
    @Override protected void implCloseChannel () throws IOException { delegate.close(); }
  }
}
