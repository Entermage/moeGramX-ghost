import java.util.*;

/** Host-only doubles. Actual controller loading and ownership methods replace the markers. */
public class EmojiStatusLoadingHarness {
  @interface Nullable {}
  interface FutureBool {boolean getBoolValue();}
  static class UI {
    static ArrayDeque<Runnable> tasks=new ArrayDeque<>();static int errors;
    static void showError(Object o){errors++;}
    static void drain(){int budget=100;while(!tasks.isEmpty()){if(--budget==0)throw new AssertionError("UI callback loop");tasks.remove().run();}}
  }
  static class Base {
    boolean destroyed;boolean isDestroyed(){return destroyed;}public void destroy(){destroyed=true;}
    void runOnUiThread(Runnable r){UI.tasks.add(r);}void runOnUiThread(Runnable r,long delay){UI.tasks.add(r);}
    /* BASE_UI */
  }
  static class TdApi {
    static class Object {int getConstructor(){return -1;}}
    static class Function<T> extends Object {}
    static class Error extends Object {static final int CONSTRUCTOR=1;int getConstructor(){return CONSTRUCTOR;}}
    static class StickerTypeCustomEmoji {}
    static class Sticker {java.lang.Object fullType;}
    static class StickerSetInfo {long id;int size=1;Sticker[] covers=new Sticker[0];java.lang.Object stickerType;StickerSetInfo(long n){id=n;}}
    static class TrendingStickerSets extends Object {static final int CONSTRUCTOR=2;int totalCount;StickerSetInfo[] sets;TrendingStickerSets(int n,long...ids){totalCount=n;sets=infos(ids);}int getConstructor(){return CONSTRUCTOR;}}
    static class StickerSets extends Object {static final int CONSTRUCTOR=3;StickerSetInfo[] sets;StickerSets(long...ids){sets=infos(ids);}int getConstructor(){return CONSTRUCTOR;}}
    static class Stickers extends Object {static final int CONSTRUCTOR=4;Sticker[] stickers=new Sticker[0];int getConstructor(){return CONSTRUCTOR;}}
    static class EmojiStatusCustomEmojis extends Object {static final int CONSTRUCTOR=5;long[] customEmojiIds=new long[]{11};int getConstructor(){return CONSTRUCTOR;}}
    static class EmojiStatusTypeCustomEmoji extends Object {static final int CONSTRUCTOR=6;int getConstructor(){return CONSTRUCTOR;}}
    static class EmojiStatus {Object type=new EmojiStatusTypeCustomEmoji();}
    static class EmojiStatuses extends Object {static final int CONSTRUCTOR=7;EmojiStatus[] emojiStatuses=new EmojiStatus[]{new EmojiStatus()};int getConstructor(){return CONSTRUCTOR;}}
    static class EmojiKeywords extends Object {String[] emojiKeywords=new String[0];}
    static class GetTrendingStickerSets extends Function<TrendingStickerSets> {int offset;GetTrendingStickerSets(StickerTypeCustomEmoji t,int o,int n){offset=o;}}
    static class GetThemedEmojiStatuses extends Function<EmojiStatusCustomEmojis> {}
    static class GetDefaultEmojiStatuses extends Function<EmojiStatusCustomEmojis> {}
    static class GetRecentEmojiStatuses extends Function<EmojiStatuses> {}
    static class GetCustomEmojiStickers extends Function<Stickers> {GetCustomEmojiStickers(long[] ids){}}
    static class GetInstalledStickerSets extends Function<StickerSets> {GetInstalledStickerSets(StickerTypeCustomEmoji t){}}
    static class SearchInstalledStickerSets extends Function<StickerSets> {SearchInstalledStickerSets(StickerTypeCustomEmoji t,String q,int n){}}
    static class SearchStickers extends Function<Stickers> {SearchStickers(StickerTypeCustomEmoji t,String q,Object o,String[] lang,int offset,int n){}}
    static class SearchEmojis extends Function<EmojiKeywords> {SearchEmojis(String q,String[] l){}}
    static StickerSetInfo[] infos(long[] ids){StickerSetInfo[] out=new StickerSetInfo[ids.length];for(int i=0;i<ids.length;i++)out[i]=new StickerSetInfo(ids[i]);return out;}
  }
  static class Client {
    interface ResultHandler {void onResult(TdApi.Object object);}
    static class Request {TdApi.Function<?> request;ResultHandler result;Request(TdApi.Function<?> q,ResultHandler r){request=q;result=r;}}
    ArrayList<Request> sent=new ArrayList<>();
    void send(TdApi.Function<?> q,ResultHandler r){sent.add(new Request(q,r));}
    void reply(int index,TdApi.Object object){sent.get(index).result.onResult(object);}
    int pages(){int n=0;for(Request r:sent)if(r.request instanceof TdApi.GetTrendingStickerSets)n++;return n;}
    int lastOffset(){return ((TdApi.GetTrendingStickerSets)sent.get(sent.size()-1).request).offset;}
  }
  interface KeywordHandler {void accept(TdApi.EmojiKeywords keywords,TdApi.Error error);}
  static class Tdlib {Client client=new Client();Client client(){return client;}void send(TdApi.SearchEmojis q,KeywordHandler h){client.send(q,o->h.accept((TdApi.EmojiKeywords)o,null));}}
  static class LongList {ArrayList<Long> values=new ArrayList<>();LongList(int n){}int size(){return values.size();}void append(long n){values.add(n);}long[] get(){return values.stream().mapToLong(v->v).toArray();}}
  static class StringUtils {static boolean isEmpty(String s){return s==null||s.isEmpty();}static boolean equalsOrBothEmpty(String a,String b){return Objects.equals(a,b)||(isEmpty(a)&&isEmpty(b));}}
  static class U {static String[] getInputLanguages(){return new String[0];}}
  static class Td {static long customEmojiId(TdApi.EmojiStatus s){return 12;}static String[] findUniqueEmojis(String[] a){return a;}}
  static class TextUtils {static String join(String join,String[] a){return String.join(join,a);}}
  static class GifFile {static class OptimizationMode {static final int EMOJI_PREVIEW=1;}}
  static class TGStickerObj {TGStickerObj(Tdlib t,TdApi.Sticker s,Object o,Object type){}void setPreviewOptimizationMode(int i){}void setIsRecent(){}void setStickerSetId(long id,Object o){}void setDataProvider(Object p){}}
  static class TGStickerSetInfo {
    long id;int size;TGStickerSetInfo(Tdlib t,TdApi.StickerSetInfo s){id=s.id;size=s.size;}TGStickerSetInfo(Tdlib t,TdApi.Sticker[] s,boolean b,int n){size=n;}
    int getSize(){return size;}void setStartIndex(int n){}void setIsDefaultEmoji(){}
  }
  static class MediaStickersAdapter {
    static class StickerHolder {static final int TYPE_NO_EMOJISETS=0,TYPE_KEYBOARD_TOP=1,TYPE_EMPTY=2,TYPE_STICKER=3,TYPE_HEADER=4,TYPE_EMOJI_STATUS_DEFAULT=5,TYPE_PROGRESS=6;}
    static class StickerItem {StickerItem(int t){}StickerItem(int t,Object o){}}
    ArrayList<StickerItem> items=new ArrayList<>();int getItemCount(){return items.size();}
    void setItem(StickerItem i){items.clear();items.add(i);}void setItems(ArrayList<StickerItem> i){items=new ArrayList<>(i);}void addItems(ArrayList<StickerItem> i){items.addAll(i);}
  }
  static class StickerSetsDataProvider {void clear(){}}
  static class EmojiMediaListController {
    static void parseTrending(Tdlib t,ArrayList<TGStickerSetInfo> parsed,ArrayList<MediaStickersAdapter.StickerItem> items,int start,TdApi.StickerSetInfo[] raw,Object provider,Object a,boolean b,boolean c,Object d){for(TdApi.StickerSetInfo s:raw){parsed.add(new TGStickerSetInfo(t,s));items.add(new MediaStickersAdapter.StickerItem(3));}}
  }
  static class Animator {boolean cancelled;void cancel(){cancelled=true;}}
  static class EmojiLayout {
    static final int STICKERS_INSTALLED_CONTROLLER_ID=1;Cache adapter=new Cache();int additions,replacements;
    static class Cache {ArrayList<Controller> controllers=new ArrayList<>();void destroyCachedItems(){for(Controller c:controllers)c.destroy();controllers.clear();}}
    void onAddStickerSection(int id,int index,TGStickerSetInfo info){additions++;}
    void setStickerSets(ArrayList<TGStickerSetInfo> s,boolean a,boolean b,boolean c,boolean d){replacements++;}
    /* LAYOUT_DESTROY */
  }
  static class Foreground {EmojiLayout foregroundEmojiLayout=new EmojiLayout();/* FOREGROUND_DESTROY */}
  static class Page extends Base {EmojiLayout emojiCustomListLayout=new EmojiLayout();Foreground foregroundEmojiLayout=new Foreground();/* PAGE_DESTROY */}
  static class Controller extends Base {
    Tdlib tdlib=new Tdlib();EmojiLayout arguments=new EmojiLayout();EmojiLayout getArguments(){return arguments;}
    volatile int stickerLoadGeneration=1;boolean loadingStickers,stickersLoaded=true,trendingLoading,canLoadMoreTrending=true;int trendingOffset,trendingSkip;
    ArrayList<TGStickerSetInfo> trendingSets=new ArrayList<>(),stickerSets=new ArrayList<>();TGStickerSetInfo lastTrendingStickerSet,lastStickerSetInfo;
    TdApi.Sticker[] pendingRecentStickers,pendingTrendingStickers;String currentTextSearchRequest,currentEmojiSearchRequest;
    MediaStickersAdapter stickersAdapter=new MediaStickersAdapter();StickerSetsDataProvider stickerSetsDataProvider;
    ArrayList<long[]> pendingChanges;Runnable onStickersLoadListener;Animator lastScrollAnimator;
    static final int MAX_EMOJI_STATUS_COUNT=1000;HashSet<Long> installed=new HashSet<>();
    boolean isContainStickerSet(TdApi.StickerSetInfo s){return installed.contains(s.id);}
    StickerSetsDataProvider stickerSetsDataProvider(){return new StickerSetsDataProvider();}
    /* METHODS */
  }
  static int checks;
  static void check(boolean v,String m){checks++;if(!v)throw new AssertionError(m);}
  static void equal(int expected,int actual,String m){check(expected==actual,m+" expected="+expected+" actual="+actual);}
  static Controller fresh(){UI.tasks.clear();UI.errors=0;return new Controller();}
  static void reply(Controller c,int index,TdApi.Object o){c.tdlib.client.reply(index,o);UI.drain();}
  static void pagesCase(){
    Controller c=fresh();c.loadNextTrending();c.loadNextTrending();equal(1,c.tdlib.client.pages(),"in-flight page cannot be requested twice");equal(0,c.tdlib.client.lastOffset(),"first raw offset");
    reply(c,0,new TdApi.TrendingStickerSets(4,10,11));equal(2,c.stickerSets.size(),"nonempty page appends");equal(2,c.tdlib.client.lastOffset(),"next offset follows raw count");
    reply(c,1,new TdApi.TrendingStickerSets(4,12,13));equal(4,c.stickerSets.size(),"last known page appends");equal(2,c.tdlib.client.pages(),"known total stops after last page");
    c=fresh();c.installed.add(10L);c.installed.add(11L);c.loadNextTrending();reply(c,0,new TdApi.TrendingStickerSets(4,10,11));
    equal(0,c.stickerSets.size(),"installed sets remain filtered");equal(2,c.tdlib.client.pages(),"filtered empty page must continue");equal(2,c.tdlib.client.lastOffset(),"filtered page still advances raw cursor");equal(2,c.trendingSkip,"filtered count retained");
    reply(c,1,new TdApi.TrendingStickerSets(4,12,13));equal(2,c.stickerSets.size(),"later unfiltered page is visible");
    for(int total:new int[]{0,1}){c=fresh();c.loadNextTrending();reply(c,0,new TdApi.TrendingStickerSets(total,10,11));equal(2,c.tdlib.client.pages(),"unknown or lagging total permits progressing page");equal(2,c.tdlib.client.lastOffset(),"unknown total still advances cursor");reply(c,1,new TdApi.TrendingStickerSets(total));equal(2,c.tdlib.client.pages(),"unknown total ends on empty raw page");}
  }
  static void stopCase(){
    Controller c=fresh();c.loadNextTrending();reply(c,0,new TdApi.TrendingStickerSets(99));
    c.loadNextTrending();c.loadNextTrending();equal(1,c.tdlib.client.pages(),"raw empty page must stop without repeating offset");check(!c.trendingLoading&&!c.canLoadMoreTrending,"empty page clears busy state");
    c=fresh();c.loadNextTrending();reply(c,0,new TdApi.Error());c.loadNextTrending();equal(1,c.tdlib.client.pages(),"error stops repeat requests");equal(1,UI.errors,"error is reported once");
    c=fresh();c.loadNextTrending();reply(c,0,new TdApi.TrendingStickerSets(1,10));c.loadNextTrending();equal(1,c.tdlib.client.pages(),"reliable total stops explicit retry");
  }
  static void searchCase(){
    Controller c=fresh();c.loadNextTrending();c.search("cat","cat-emoji");int generation=c.stickerLoadGeneration;
    reply(c,0,new TdApi.TrendingStickerSets(1,100));equal(0,c.stickerSets.size(),"old trending response cannot enter new search");equal(0,c.trendingOffset,"old network page cannot advance new raw cursor");
    c=fresh();c.loadNextTrending();c.tdlib.client.reply(0,new TdApi.TrendingStickerSets(1,100));c.search("dog","dog-emoji");UI.drain();equal(0,c.stickerSets.size(),"old queued page cannot enter new search");equal(0,c.trendingOffset,"queued page cannot advance new cursor");
    c=fresh();Client.ResultHandler old=c.stickerSetsHandler(false,c.stickerLoadGeneration);old.onResult(new TdApi.StickerSets(100));c.search("new","new-emoji");UI.drain();equal(0,c.stickerSets.size(),"queued old initial load cannot replace search");equal(0,c.arguments.replacements-1,"only search reset replaces displayed sections");
    c=fresh();old=c.stickerSetsHandler(false,c.stickerLoadGeneration);c.search("new","new-emoji");old.onResult(new TdApi.StickerSets(100));UI.drain();equal(0,c.stickerSets.size(),"old initial network result is ignored");
    c=fresh();int[] after={0};Client.ResultHandler trend=c.trendingStickersHandler(()->after[0]++,c.stickerLoadGeneration),service=c.serviceStickersHandler(null,c.stickerLoadGeneration);c.search("new","new-emoji");int requests=c.tdlib.client.sent.size();trend.onResult(new TdApi.Stickers());service.onResult(new TdApi.Stickers());equal(0,after[0],"old initial continuation cannot run");equal(requests,c.tdlib.client.sent.size(),"old initial handler cannot send next request");
    c=fresh();c.loadStickers();equal(1,c.tdlib.client.sent.size(),"default initial chain starts once");c.search("new","new-emoji");requests=c.tdlib.client.sent.size();reply(c,0,new TdApi.EmojiStatusCustomEmojis());equal(requests,c.tdlib.client.sent.size(),"old status-list helper cannot continue after reload");
    c=fresh();c.search("new","new-emoji");reply(c,0,new TdApi.Stickers());check(c.tdlib.client.sent.get(1).request instanceof TdApi.SearchInstalledStickerSets,"current search keeps original installed query sequence");reply(c,1,new TdApi.StickerSets(200));equal(1,c.stickerSets.size(),"current generation initial result applies");equal(200,(int)c.stickerSets.get(0).id,"new search data wins");equal(1,c.tdlib.client.pages(),"current search retains existing Trending sequence");
  }
  static void destroyCase(){
    Controller c=fresh();c.loadNextTrending();c.lastScrollAnimator=new Animator();Page p=new Page();p.emojiCustomListLayout.adapter.controllers.add(c);Controller hidden=new Controller();p.foregroundEmojiLayout.foregroundEmojiLayout.adapter.controllers.add(hidden);
    p.destroy();check(c.isDestroyed(),"hidden emoji controller must be destroyed");check(hidden.isDestroyed(),"foreground emoji controller must be destroyed");check(c.lastScrollAnimator.cancelled,"closing cancels group scroll animator");
    reply(c,0,new TdApi.TrendingStickerSets(2,10));c.loadNextTrending();c.loadStickers();equal(1,c.tdlib.client.sent.size(),"closed controller cannot process or continue late page");equal(0,c.stickerSets.size(),"closed controller receives no late items");int generation=c.stickerLoadGeneration;p.destroy();equal(generation,c.stickerLoadGeneration,"repeated owner destroy is harmless");
    c=fresh();c.loadNextTrending();c.tdlib.client.reply(0,new TdApi.TrendingStickerSets(2,10));c.destroy();UI.drain();equal(0,c.stickerSets.size(),"closing before queued UI delivery drops page");equal(1,c.tdlib.client.sent.size(),"queued UI cannot request next page after close");
    c=fresh();c.loadStickers();c.destroy();reply(c,0,new TdApi.EmojiStatusCustomEmojis());equal(1,c.tdlib.client.sent.size(),"closed initial status callback cannot continue");
  }
  public static void main(String[] args){switch(args[0]){case "pages":pagesCase();break;case "stop":stopCase();break;case "search":searchCase();break;case "destroy":destroyCase();break;default:throw new AssertionError();}System.out.println(args[0]+": "+checks+" production loading checks passed");}
}
