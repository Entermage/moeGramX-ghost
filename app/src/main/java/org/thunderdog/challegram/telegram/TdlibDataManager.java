/*
 * This file is a part of Telegram X
 * Copyright © 2014 (tgx-android@pm.me)
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 *
 * File created on 18/10/2022, 01:17.
 */
package org.thunderdog.challegram.telegram;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.UiThread;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.util.BatchOperationHandler;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import me.vkryl.core.reference.ReferenceList;
import me.vkryl.core.reference.ReferenceMap;

public abstract class TdlibDataManager<Key, Value extends TdApi.Object, Result extends TdlibDataManager.AbstractEntry<Key, Value>> implements CleanupStartupDelegate {
  public static abstract class AbstractEntry<K, V extends TdApi.Object> {
    public final K key;
    public final @Nullable V value;
    public final @Nullable TdApi.Error error;

    public AbstractEntry (@NonNull K key, @Nullable V value, @Nullable TdApi.Error error) {
      this.key = key;
      this.value = value;
      this.error = error;
      if (error == null && value == null)
        throw new IllegalStateException();
    }

    public boolean isNotFound () {
      return error != null || value == null;
    }
  }

  public interface Watcher<Key, Value extends TdApi.Object, Result extends TdlibDataManager.AbstractEntry<Key, Value>> {
    void onEntryLoaded (TdlibDataManager<Key, Value, Result> context, Result entry);
  }

  protected abstract Result newEntry (@NonNull Key key, @Nullable Value value, @Nullable TdApi.Error error);

  protected final Tdlib tdlib;

  private final Object dataLock = new Object();
  private final Map<Key, Result> entries = new HashMap<>();
  private final Set<Key> postponedKeys = new HashSet<>();
  private final Set<Key> loadingKeys = new HashSet<>();
  private final ReferenceMap<Key, Watcher<Key, Value, Result>> watcherReferences = new ReferenceMap<>(true);
  private final Map<Key, List<Watcher<Key, Value, Result>>> watchers = new LinkedHashMap<>();

  private int contextId;

  protected TdlibDataManager (Tdlib tdlib) {
    this.tdlib = tdlib;
    tdlib.listeners().addCleanupListener(this);
  }

  // Listeners

  /**
   * Whether a client restart ends the waits of this manager's watchers with an uncached error. Otherwise
   * they stay registered and receive the next client's answer for their key (custom emoji, for example,
   * would show an error entry as "not found").
   */
  protected boolean endsWaitsOnRestart () {
    return false;
  }

  @Override
  public final void onPerformRestart () {
    final boolean endWaits = endsWaitsOnRestart();
    final Map<Key, List<Watcher<Key, Value, Result>>> cancelledWatchers;
    final Map<Key, ReferenceList<Watcher<Key, Value, Result>>> cancelledReferences;
    synchronized (dataLock) {
      contextId++;
      entries.clear();
      // Results of the closed client are dropped by contextId. Release their keys so this same
      // instance requests them again on the next client.
      loadingKeys.clear();
      postponedKeys.clear();
      if (!endWaits) {
        return;
      }
      cancelledWatchers = new LinkedHashMap<>(watchers);
      watchers.clear();
      // Watchers are only added under dataLock: detach the weak ones of the closed client in this
      // same section, so a watcher registered after it stays for the next client's request.
      cancelledReferences = removeAllReferences();
    }
    for (Map.Entry<Key, ReferenceList<Watcher<Key, Value, Result>>> pair : cancelledReferences.entrySet()) {
      List<Watcher<Key, Value, Result>> target = cancelledWatchers.get(pair.getKey());
      if (target == null) cancelledWatchers.put(pair.getKey(), target = new ArrayList<>());
      for (Watcher<Key, Value, Result> watcher : pair.getValue()) target.add(watcher);
      pair.getValue().clear();
    }
    if (!cancelledWatchers.isEmpty()) {
      tdlib.ui().post(() -> notifyCancelled(cancelledWatchers));
    }
  }

  private Map<Key, ReferenceList<Watcher<Key, Value, Result>>> removeAllReferences () {
    Map<Key, ReferenceList<Watcher<Key, Value, Result>>> removed = new LinkedHashMap<>();
    synchronized (watcherReferences.mapUnchecked()) {
      Set<Key> keys = watcherReferences.keySetUnchecked();
      if (keys != null) {
        for (Key key : new ArrayList<>(keys)) {
          ReferenceList<Watcher<Key, Value, Result>> list = watcherReferences.removeAll(key);
          if (list != null) removed.put(key, list);
        }
      }
    }
    return removed;
  }

  private void notifyCancelled (Map<Key, List<Watcher<Key, Value, Result>>> cancelledWatchers) {
    for (Map.Entry<Key, List<Watcher<Key, Value, Result>>> pair : cancelledWatchers.entrySet()) {
      // A terminal, uncached error: the next find() requests the key again.
      Result entry = newEntry(pair.getKey(), null, new TdApi.Error(CANCELLED_ERROR_CODE, CANCELLED_ERROR_MESSAGE));
      for (Watcher<Key, Value, Result> watcher : pair.getValue()) {
        watcher.onEntryLoaded(this, entry);
      }
    }
  }

  public static final int CANCELLED_ERROR_CODE = 500;
  public static final String CANCELLED_ERROR_MESSAGE = "Request cancelled by client restart";

  // Impl

  @UiThread
  public final Result find (Key key) {
    synchronized (dataLock) {
      return entries.get(key);
    }
  }

  public interface Replacer<Value extends TdApi.Object> {
    @Nullable
    Value replace (@Nullable Value oldValue, @Nullable TdApi.Error oldError);
  }

  @UiThread
  public final boolean replaceExisting (Key key, Replacer<Value> replacer) {
    synchronized (dataLock) {
      Result entry = entries.get(key);
      if (entry != null) {
        Value newValue = replacer.replace(entry.value, entry.error);
        if (newValue != null) {
          Result newEntry = newEntry(key, newValue, null);
          entries.put(key, newEntry);
          return true;
        }
      }
    }
    return false;
  }

  public interface Callback<T> {
    void onEntryFound (T entry, boolean inPlace);
  }

  @UiThread
  @Nullable
  public final Result findOrRequest (Key key, @Nullable Callback<Result> callback) {
    Watcher<Key, Value, Result> watcher;
    if (callback != null) {
      watcher = (context, entry) ->
        callback.onEntryFound(entry, false);
    } else {
      watcher = null;
    }
    Result entry = findOrPostponeRequest(key, watcher, true);
    if (entry != null) {
      if (callback != null) {
        callback.onEntryFound(entry, true);
      }
    } else {
      performPostponedRequest(key);
    }
    return entry;
  }

  @Nullable
  public final Result findOrPostponeRequest (Key key, Watcher<Key, Value, Result> watcher) {
    return findOrPostponeRequest(key, watcher, false);
  }

  @Nullable
  public final Result findOrPostponeRequest (Key key, Watcher<Key, Value, Result> watcher, boolean strongReference) {
    synchronized (dataLock) {
      Result entry = entries.get(key);
      if (entry != null) {
        return entry;
      }
      if (!loadingKeys.contains(key)) {
        postponedKeys.add(key);
      }
      if (watcher != null) {
        if (strongReference) {
          addWatcherImpl(key, watcher);
        } else {
          watcherReferences.add(key, watcher);
        }
      }
      return null;
    }
  }

  private void addWatcherImpl (Key key, Watcher<Key, Value, Result> watcher) {
    List<Watcher<Key, Value, Result>> list = watchers.get(key);
    if (list != null && !list.contains(watcher)) {
      list.add(watcher);
    } else {
      list = new ArrayList<>();
      list.add(watcher);
      watchers.put(key, list);
    }
  }

  public final void forgetWatcher (Key key, Watcher<Key, Value, Result> watcher) {
    watcherReferences.remove(key, watcher);
  }

  private final BatchOperationHandler delayedHandler = new BatchOperationHandler(this::performPostponedRequests, 10);

  @UiThread
  public void performPostponedRequest (Key key) {
    int contextId;
    synchronized (dataLock) {
      if (postponedKeys.isEmpty() || !postponedKeys.remove(key)) {
        return;
      }
      loadingKeys.add(key);
      contextId = this.contextId;
    }
    requestData(contextId, Set.of(key));
  }

  @UiThread
  public void performPostponedRequestsDelayed () {
    delayedHandler.performOperation();
  }

  @UiThread
  public void performPostponedRequests () {
    final Set<Key> keysToRequest;
    int contextId;
    synchronized (dataLock) {
      if (postponedKeys.isEmpty()) {
        return;
      }
      loadingKeys.addAll(postponedKeys);
      keysToRequest = new HashSet<>(postponedKeys);
      postponedKeys.clear();
      contextId = this.contextId;
    }
    requestData(contextId, keysToRequest);
  }

  protected final boolean isCancelled (int contextId) {
    synchronized (dataLock) {
      return this.contextId != contextId;
    }
  }

  @UiThread
  protected abstract void requestData (int contextId, Collection<Key> keysToRequest);

  @TdlibThread
  protected final void processData (int contextId, @NonNull Key key, @Nullable Value value) {
    if (value != null) {
      processEntry(contextId, newEntry(key, value, null));
    } else {
      processError(contextId, key, new TdApi.Error(404, "Not Found"));
    }
  }

  /** Discard only this failed response; never removes a newer successful update. */
  protected final void forgetError (int requestContextId, Key key, TdApi.Error error) {
    synchronized (dataLock) {
      Result entry = entries.get(key);
      if (contextId == requestContextId && entry != null && entry.error == error) entries.remove(key);
    }
  }

  @TdlibThread
  protected final void processError (int contextId, @NonNull Key key, @NonNull TdApi.Error error) {
    processEntry(contextId, newEntry(key, null, error));
  }

  /** The request ended without an answer (its client closed): release the key without caching an error. */
  protected final void processCancelled (int contextId, @NonNull Key key, @NonNull TdApi.Error error) {
    List<Watcher<Key, Value, Result>> watcherList;
    ReferenceList<Watcher<Key, Value, Result>> referenceList;
    synchronized (dataLock) {
      if (this.contextId != contextId || !loadingKeys.remove(key))
        return;
      // Same section as the key release: a watcher added after it postpones a new request instead.
      watcherList = watchers.remove(key);
      referenceList = watcherReferences.removeAll(key);
    }
    Result entry = newEntry(key, null, error);
    if (referenceList != null) {
      for (Watcher<Key, Value, Result> watcher : referenceList) {
        watcher.onEntryLoaded(this, entry);
      }
      referenceList.clear();
    }
    if (watcherList != null) {
      for (Watcher<Key, Value, Result> watcher : watcherList) {
        watcher.onEntryLoaded(this, entry);
      }
    }
  }

  @TdlibThread
  private void processEntry (int contextId, Result entry) {
    List<Watcher<Key, Value, Result>> watcherList;
    ReferenceList<Watcher<Key, Value, Result>> referenceList;
    synchronized (dataLock) {
      if (this.contextId != contextId)
        return;
      entries.put(entry.key, entry);
      watcherList = watchers.remove(entry.key);
      // Detach before a restart can start the next generation.
      referenceList = watcherReferences.removeAll(entry.key);
    }
    if (referenceList != null) {
      for (Watcher<Key, Value, Result> watcher : referenceList) {
        watcher.onEntryLoaded(this, entry);
      }
      referenceList.clear();
    }
    if (watcherList != null) {
      for (Watcher<Key, Value, Result> watcher : watcherList) {
        watcher.onEntryLoaded(this, entry);
      }
    }
    synchronized (dataLock) {
      if (this.contextId != contextId)
        return;
      loadingKeys.remove(entry.key);
    }
  }

}
