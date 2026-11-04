import java.util.ArrayList;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

public class TwoPaneProxySourceHarness {
  interface TdlibDelegate { Activity context(); Tdlib tdlib(); }
  interface OptionDelegate { boolean onOptionItemPressed(Object view, int id); }
  static final class Activity {
    final Navigation navigation=new Navigation();
    Navigation navigation() { return navigation; }
  }
  static final class Navigation {
    ViewController<?> current, opened;
    ViewController<?> getCurrentStackItem() { return current; }
    void navigateTo(ViewController<?> value) { opened=value; }
  }
  static class Delegate implements TdlibDelegate {
    final Activity activity; final Tdlib tdlib;
    Delegate(Activity activity, Tdlib tdlib) { this.activity=activity; this.tdlib=tdlib; }
    public Activity context() { return activity; } public Tdlib tdlib() { return tdlib; }
  }
  static class ViewController<T> extends Delegate {
    int menuCalls, cameraCalls; ViewController<?> opened; OptionDelegate menuCallback;
    ViewController(Activity a,Tdlib t) { super(a,t); }
    void showOptions(String info,int[] ids,String[] strings,OptionDelegate callback) { menuCalls++;menuCallback=callback; }
    void navigateTo(ViewController<?> value) { opened=value; }
    void openInAppCamera(CameraOpenOptions options) { cameraCalls++; }
    static class CameraOpenOptions {
      CameraOpenOptions ignoreAnchor(boolean v) { return this; }
      CameraOpenOptions noTrace(boolean v) { return this; }
      CameraOpenOptions allowSystem(boolean v) { return this; }
      CameraOpenOptions optionalMicrophone(boolean v) { return this; }
      CameraOpenOptions qrModeSubtitle(int v) { return this; }
      CameraOpenOptions mode(int v) { return this; }
      CameraOpenOptions qrCodeListener(Consumer<String> v) { return this; }
    }
  }
  static final class EditProxyController extends ViewController<Void> {
    static final int MODE_SOCKS5=1,MODE_MTPROTO=2,MODE_HTTP=3; Args args;
    EditProxyController(Activity a,Tdlib t) { super(a,t); }
    void setArguments(Args value) { args=value; }
    static class Args { final int mode; Args(int v) { mode=v; } }
  }
  static final class SettingsProxyController extends ViewController<Void> {
    SettingsProxyController(Activity a,Tdlib t) { super(a,t); }
  }
  static final class CameraController { static final int MODE_QR=1; }
  static final class Settings {
    static final Settings INSTANCE=new Settings(); static int proxyCount;
    static Settings instance() { return INSTANCE; } int getAvailableProxyCount() { return proxyCount; }
  }
  static final class Tdlib {
    boolean qr;
    boolean allowQrLoginCamera() { return qr; }
    void send(TdApi.GetInternalLinkType request,BiConsumer<TdApi.InternalLinkType,Object> callback) {}
  }
  static final class TdApi {
    static class Proxy {}
    static class GetInternalLinkType { GetInternalLinkType(String s) {} }
    static class InternalLinkType { int getConstructor() { return 1; } }
    static class InternalLinkTypeProxy extends InternalLinkType { static final int CONSTRUCTOR=1; Proxy proxy; }
  }
  static final class IntList {
    final ArrayList<Integer> values=new ArrayList<>(); IntList(int capacity) {}
    void append(int value) { values.add(value); } int size() { return values.size(); }
    int get(int i) { return values.get(i); } int[] get() { return values.stream().mapToInt(Integer::intValue).toArray(); }
  }
  static final class StringList {
    final ArrayList<String> values=new ArrayList<>(); StringList(int capacity) {}
    void append(int value) { values.add(String.valueOf(value)); } String[] get() { return values.toArray(new String[0]); }
  }
  static final class Lang { static String getString(int id) { return String.valueOf(id); } }
  static final class R {
    static final class id { static final int btn_proxyTelegram=1,btn_proxySocks5=2,btn_proxyHttp=3,btn_proxyQr=4; }
    static final class string {
      static final int AddMtprotoProxy=1,AddSocks5Proxy=2,AddHttpProxy=3,MtprotoProxy=4,Socks5Proxy=5,HttpProxy=6,
        ScanQR=7,ScanQRFullSubtitleProxy=8,ProxyInfo=9;
    }
  }
  static class ProxyUi {
    final Tdlib tdlib;
    ProxyUi(Tdlib t) { tdlib=t; }
    void postDelayed(Runnable r,long delay) { r.run(); } void post(Runnable r) { r.run(); }
    void openProxyAlert(TdlibDelegate context,TdApi.Proxy proxy) {}
    __METHODS__
  }
  static int checks;
  static void check(boolean value,String message) { checks++; if(!value)throw new AssertionError(message); }
  public static void main(String[] args) {
    Activity a=new Activity(); Tdlib t=new Tdlib(); ProxyUi ui=new ProxyUi(t);
    ViewController<?> right=new ViewController<>(a,t),left=new ViewController<>(a,t);
    a.navigation.current=right; Settings.proxyCount=0;
    ui.openProxySettings(left,false);
    check(left.menuCalls==1 && right.menuCalls==0,"explicit left source owns the type menu");
    check(left.opened==null && right.opened==null,"showing menu does not navigate");
    for(int[] pair:new int[][]{{R.id.btn_proxySocks5,1},{R.id.btn_proxyTelegram,2},{R.id.btn_proxyHttp,3}}) {
      left.menuCallback.onOptionItemPressed(null,pair[0]);
      check(right.opened instanceof EditProxyController && ((EditProxyController)right.opened).args.mode==pair[1],
        "proxy editor keeps the primary navigation and requested mode");
      check(left.opened==null,"type selection does not replace the list pane");
    }
    t.qr=true;ui.addNewProxy(left,true);left.menuCallback.onOptionItemPressed(null,R.id.btn_proxyQr);
    check(right.cameraCalls==1 && left.cameraCalls==0,"QR camera keeps its original primary controller");
    ui.addNewProxy(new Delegate(a,t),false);
    check(right.menuCalls==1,"delegate without explicit controller retains current-stack fallback");
    ui.addNewProxy(right,false);
    check(right.menuCalls==2,"explicit right source keeps right menu behavior");
    Settings.proxyCount=2;ui.openProxySettings(left,false);
    check(a.navigation.opened instanceof SettingsProxyController,"existing proxy list still opens in primary navigation");
    check(left.menuCalls==2,"existing proxies do not open type menu");
    a.navigation.current=null;ui.addNewProxy(new Delegate(a,t),false);
    check(right.menuCalls==2,"missing current controller retains safe no-op");
    System.out.println("Two-pane proxy source: "+checks+" production checks passed (JVM state doubles)");
  }
}
