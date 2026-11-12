"""Production language/proxy restoration methods with JVM data-store doubles.
These are state regression tests, not Telegram/network/Android end-to-end tests.
"""
import re
import unittest
from test_upstream_backports import BASE, CHECK, method, run_java


def language_source():
    return CHECK + '''
String languagePackId="en"; Object countries=new Object(); int updates; final Object dataLock=new Object(); long countriesGeneration;
Object client(){return this;} void updateLanguageParameters(Object c,boolean b){updates++;}
static class StringUtils {static boolean equalsOrBothEmpty(String a,String b){return Objects.equals(a,b);}}
''' + method('telegram/Tdlib.java', 'private boolean setLanguagePackIdImpl (') + '''
public static void main(String[] args){
 Backport b=new Backport(); Object cache=b.countries;
 check(!b.setLanguagePackIdImpl("en",true)&&b.countries==cache&&b.updates==0);
 check(b.setLanguagePackIdImpl("zh-hans",true)&&b.languagePackId.equals("zh-hans")&&b.countries==null&&b.updates==1);
 b.countries=new Object();check(b.setLanguagePackIdImpl("ja",false)&&b.countries==null&&b.updates==1);
 check(!b.setLanguagePackIdImpl("ja",false));
}
'''


def proxy_source():
    source=(BASE/'unsorted/Settings.java').read_text()
    constants='\n'.join(line for line in source.splitlines() if re.search(r'static final (?:String KEY_PROXY|int PROXY_ID_NONE)',line))
    return CHECK + constants + '''
static class Blob {}
static class Log {static void w(String text,Object...args){}}
static class StringUtils {static int parseInt(String s){try{return Integer.parseInt(s);}catch(Exception e){return 0;}}}
static class ArrayUtils {static int indexOf(int[] a,int n){for(int i=0;i<a.length;i++)if(a[i]==n)return i;return -1;}}
static class SparseArrayCompat<T> {Map<Integer,T> m=new HashMap<>();void put(int i,T t){m.put(i,t);}T get(int i){return m.get(i);}}
static class Proxy implements Comparable<Proxy> {
 static int ORDER_UNSET=-1;int id,order,successfulConnectionsCount;String description;
 long lastConnectionTime,lastConnectionDuration,lastPingTime,lastPingResult;
 Proxy(int id){this.id=id;}public int compareTo(Proxy p){return Integer.compare(order,p.order);}
}
static class LevelDB {
 static class Entry {
  String k;Object v;Entry(String k,Object v){this.k=k;this.v=v;}
  String key(){return k;} byte[] asByteArray(){return (byte[])v;}String asString(){return (String)v;}
  int asInt(){return (int)v;}long[] asLongArray(){if(!(v instanceof long[]))throw new IllegalArgumentException();return (long[])v;}
 }
 TreeMap<String,Entry> data=new TreeMap<>();int[] order={7,2};
 void put(String k,Object v){data.put(k,new Entry(k,v));}
 int[] getIntArray(String key){return order;}List<Entry> find(String prefix){return new ArrayList<>(data.values());}
}
LevelDB pmc=new LevelDB();List<Integer> removed=new ArrayList<>();
Proxy readProxy(int id,byte[] data,Blob blob){return data.length==0?null:new Proxy(id);}
void removeProxy(int id){removed.add(id);}
''' + method('unsorted/Settings.java','private @NonNull List<Proxy> loadAvailableProxies ()') + '''
public static void main(String[] args){
 Backport b=new Backport();
 for(int id:new int[]{2,7}){
  b.pmc.put(KEY_PROXY_PREFIX_CONFIG+id,new byte[]{1});
  b.pmc.put(KEY_PROXY_PREFIX_DESCRIPTION+id,"proxy-"+id);
  b.pmc.put(KEY_PROXY_PREFIX_CONNECTED_COUNT+id,id*3);
  b.pmc.put(KEY_PROXY_PREFIX_LAST_CONNECTION+id,new long[]{id*10,id*20});
  b.pmc.put(KEY_PROXY_PREFIX_LAST_PING+id,new long[]{id*30,id*40});
 }
 b.pmc.put(KEY_PROXY_PREFIX_CONFIG+9,new byte[0]);
 b.pmc.put(KEY_PROXY_PREFIX_DESCRIPTION+9,"orphan");
 List<Proxy> p=b.loadAvailableProxies();check(p.size()==2&&p.get(0).id==7&&p.get(1).id==2);
 for(Proxy v:p){check(v.description.equals("proxy-"+v.id));check(v.successfulConnectionsCount==v.id*3);check(v.lastConnectionTime==v.id*10&&v.lastConnectionDuration==v.id*20);check(v.lastPingTime==v.id*30&&v.lastPingResult==v.id*40);}
 check(b.removed.equals(List.of(9)));
 b.pmc.put(KEY_PROXY_PREFIX_LAST_CONNECTION+2,new long[0]);b.pmc.put(KEY_PROXY_PREFIX_LAST_PING+7,new long[]{99});
 p=b.loadAvailableProxies();check(p.get(1).lastConnectionTime==0&&p.get(1).lastConnectionDuration==0);check(p.get(0).lastPingTime==99&&p.get(0).lastPingResult==0);
}
'''


def countries_source():
    return CHECK + r"""
static class TdApi {static class GetCountries {} static class CountryInfo {String name;CountryInfo(String n){name=n;}}static class Countries {CountryInfo[] countries;Countries(String n){countries=new CountryInfo[]{new CountryInfo(n)};}}}
interface RunnableData<T> {void runWithData(T t);}
interface Response {void accept(TdApi.Countries c,Object error);}
List<Response> pending=new ArrayList<>();void send(TdApi.GetCountries request,Response callback){pending.add(callback);}
final Object dataLock=new Object();long countriesGeneration;TdApi.Countries countries;String languagePackId="en";
Object client(){return this;}void updateLanguageParameters(Object c,boolean b){}
static class StringUtils {static boolean equalsOrBothEmpty(String a,String b){return Objects.equals(a,b);}}
""".replace('\n+','\n') + method('telegram/Tdlib.java','private boolean setLanguagePackIdImpl (') + method('telegram/Tdlib.java','public void getCountries (') + r"""
public static void main(String[] args){
 Backport b=new Backport();List<String> answers=new ArrayList<>();
 b.getCountries(c->answers.add(c[0].name));check(b.pending.size()==1);
 b.setLanguagePackIdImpl("ja",false);b.pending.get(0).accept(new TdApi.Countries("English"),null);
 check(answers.isEmpty()&&b.countries==null&&b.pending.size()==2);
 b.pending.get(1).accept(new TdApi.Countries("Japanese"),null);check(answers.equals(List.of("Japanese")));
 b.getCountries(c->answers.add(c[0].name));check(b.pending.size()==2&&answers.equals(List.of("Japanese","Japanese")));
 b.setLanguagePackIdImpl("fr",true);b.getCountries(c->check(c.length==0));b.pending.get(2).accept(null,new Object());check(b.countries==null);
}
""".replace('\n+','\n')


class UpstreamMergeStateTest(unittest.TestCase):
    def test_old_country_request_is_retried(self):
        result=run_java(countries_source());self.assertEqual(result.returncode,0,result.stderr)

    def test_stale_country_overwrite_is_rejected(self):
        result=run_java(countries_source().replace('stale = generation != countriesGeneration;', 'stale = false;'))
        self.assertNotEqual(result.returncode,0)

    def test_language_switch_invalidates_cache(self):
        result=run_java(language_source());self.assertEqual(result.returncode,0,result.stderr)

    def test_language_self_comparison_is_rejected(self):
        result=run_java(language_source().replace('equalsOrBothEmpty(this.languagePackId, languagePackId)','equalsOrBothEmpty(languagePackId, languagePackId)'))
        self.assertNotEqual(result.returncode,0)

    def test_restore_multiple_proxies_by_id(self):
        result=run_java(proxy_source());self.assertEqual(result.returncode,0,result.stderr)

    def test_old_key_switch_is_rejected(self):
        result=run_java(proxy_source().replace('switch (subKey)','switch (key)'))
        self.assertNotEqual(result.returncode,0)


if __name__=='__main__': unittest.main()
