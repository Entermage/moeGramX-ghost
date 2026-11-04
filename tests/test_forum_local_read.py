"""Compile production native read/merge and persistence code; no Telegram RPCs."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
TD_SOURCE = ROOT / 'tdlib/source/td'

PREAMBLE = r'''
#include <algorithm>
#include <cstdint>
#include <memory>
#include <vector>
#include <stdexcept>
#include <iostream>
namespace td {
using int32=int32_t;using int64=int64_t;using std::min;using std::max;template<class T>using vector=std::vector<T>;
struct MessageId {
 int64 id=0;MessageId()=default;explicit MessageId(int64 n):id(n){}
 bool is_valid()const{return id>0;}int64 get()const{return id;}
 bool operator<(MessageId o)const{return id<o.id;}bool operator>(MessageId o)const{return id>o.id;}
 bool operator<=(MessageId o)const{return id<=o.id;}bool operator>=(MessageId o)const{return id>=o.id;}
 bool operator==(MessageId o)const{return id==o.id;}bool operator!=(MessageId o)const{return id!=o.id;}
};
struct ForumTopic {
 bool is_short_=false,is_pinned_=false;
 int32 unread_count_=0,server_unread_count_=0;
 MessageId last_message_id_,last_read_inbox_message_id_,server_last_read_inbox_message_id_,last_read_outbox_message_id_;
 int32 unread_mention_count_=0,unread_reaction_count_=0,unread_poll_vote_count_=0,notification_settings_=0;
 std::unique_ptr<int> draft_message_;
 void preserve_local_read(const ForumTopic &previous);
 vector<int64> get_local_read_state()const;
 void preserve_local_read(const vector<int64>&state);
 bool read_inbox_messages(MessageId id,int32 count);
 bool update_last_read_inbox_message_id(MessageId id,int32 count,MessageId last=MessageId());
 void update_last_message_id(MessageId id){if(id.is_valid())last_message_id_=id;}
};
}
'''

MAIN = r'''
using namespace td;
int checks=0;void check(bool b,const char*m){++checks;if(!b)throw std::runtime_error(m);}
ForumTopic server(int64 read,int count,int64 top){ForumTopic s;s.last_read_inbox_message_id_=s.server_last_read_inbox_message_id_=MessageId(read);s.unread_count_=s.server_unread_count_=count;s.last_message_id_=MessageId(top);return s;}
void state(const ForumTopic&s,int64 read,int count){check(s.last_read_inbox_message_id_.get()==read,"read frontier regressed");check(s.unread_count_==count,"wrong remaining unread");}
ForumTopic refresh(const ForumTopic&old,int64 read,int count,int64 top){auto s=server(read,count,top);s.preserve_local_read(old);return s;}
int main(){
 auto s=server(100,10,200);
 check(s.read_inbox_messages(MessageId(130),3),"partial read changed");state(s,130,7);
 check(!s.read_inbox_messages(MessageId(130),3),"duplicate viewport must not subtract twice");
 s=refresh(s,100,10,200);state(s,130,7);
 s=refresh(s,100,12,220);state(s,130,9);
 s=refresh(s,100,12,220);state(s,130,9);
 // Same-frontier server updates must update counts; old native method ignored them.
 check(s.update_last_read_inbox_message_id(MessageId(100),13,MessageId(230)),"count-only server update lost");state(s,130,10);
 s.read_inbox_messages(MessageId(230),1);state(s,230,0); // jump reaches actual latest, even across unloaded history
 s=refresh(s,100,13,230);state(s,230,0);
 auto disk=s.get_local_read_state();check(disk.size()==6,"server baseline lost on disk");
 auto reopened=server(100,13,230);reopened.preserve_local_read(disk);state(reopened,230,0);
 check(reopened.get_local_read_state()==disk,"server baseline lost on disk");
 reopened=refresh(reopened,100,14,240);state(reopened,230,1);
 reopened=refresh(reopened,100,16,260);state(reopened,230,3);
 reopened=refresh(reopened,150,8,260);state(reopened,230,3); // another device reads old messages, no new tail
 // Unknown overlap plus new arrivals must retain unread instead of falsely clearing them.
 reopened=refresh(reopened,180,7,270);state(reopened,230,7);
 reopened=refresh(reopened,260,1,270);state(reopened,260,1); // server caught up; stop subtracting local reads
 reopened=refresh(reopened,270,0,270);state(reopened,270,0);
 check(!reopened.update_last_read_inbox_message_id(MessageId(100),99),"late server update regressed snapshot");state(reopened,270,0);
 // Missing, malformed, newer-version and negative persistence records are ignored.
 auto restored=server(100,10,200);restored.preserve_local_read(vector<int64>{});state(restored,100,10);
 restored.preserve_local_read(vector<int64>{2,200,0,100,10,200});state(restored,100,10);
 restored.preserve_local_read(vector<int64>{1,200,-1,100,10,200});state(restored,100,10);
 restored.read_inbox_messages(MessageId(200),1);auto saved=restored.get_local_read_state();
 restored=server(100,10,200);restored.preserve_local_read(saved);state(restored,200,0);
 check(reopened.get_local_read_state().empty(),"server catch-up did not retire local state");
 // Deletion plus a new arrival may leave the aggregate server count unchanged.
 auto before_delete=server(100,10,200);before_delete.read_inbox_messages(MessageId(200),1);
 auto after_delete=refresh(before_delete,100,10,210);state(after_delete,200,1);
 // Topic instances are independent. Reading one never changes its sibling.
 auto sibling=server(100,12,220);state(sibling,100,12);
 // Outgoing-only views do not subtract incoming unread until actually reaching the tail.
 auto outgoing=server(100,10,200);outgoing.read_inbox_messages(MessageId(130),0);state(outgoing,130,10);
 std::cout<<"PASS "<<checks<<" native read/merge/persistence-state assertions\n";
}
'''

class ForumLocalReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # CI runs the regressions before it patches the TDLib checkout: apply the Ghost patch to a copy.
        cls.temp=tempfile.TemporaryDirectory(prefix='forum-read-patched-');patched=Path(cls.temp.name)
        patch=ROOT/'patches/tdlib-ghost-mode.patch'
        for name in re.findall(r'^--- a/(.+)$',patch.read_text(),re.M):
            (patched/name).parent.mkdir(parents=True,exist_ok=True)
            (patched/name).write_bytes(subprocess.check_output(['git','-C',str(TD_SOURCE),'show','HEAD:'+name]))
        subprocess.run(['git','apply',str(patch)],cwd=patched,check=True)
        cls.native=patched/'td/telegram'

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_production_manager_keeps_ghost_reads_local(self):
        method=block(self.native/'ForumTopicManager.cpp','void ForumTopicManager::read_forum_topic_messages(')
        source=r'''
#include <vector>
#include <sstream>
#include <memory>
#include <stdexcept>
#include <functional>
using int32=int;template<class T>using vector=std::vector<T>;
using MessageId=int;using DialogId=int;using ForumTopicId=int;
enum class MessageType{Server};
struct ReadForumTopicQuery {int sent=0;void send(int,int,int){sent++;}};
struct Auth{bool is_bot(){return false;}};
struct Options{bool ghost=true;bool get_option_boolean(const char*){return ghost;}};
struct Messages{std::function<bool(int)>get_is_counted_as_unread(int,MessageType){return [](int id){return id!=140;};}};
struct Td{Auth auth;Auth*auth_manager_=&auth;Options options;Options*option_manager_=&options;Messages messages;Messages*messages_manager_=&messages;ReadForumTopicQuery query;template<class T>T*create_handler(){return &query;}};
struct TopicState{int read=100,count=10;int get_last_read_inbox_message_id(){return read;}bool read_inbox_messages(int id,int n){if(id<=read)return false;read=id;count-=n;return true;}};
struct Topic{std::unique_ptr<TopicState>topic_=std::make_unique<TopicState>();};
struct ForumTopicManager{Td*td_;Topic topic;int updates=0;Topic*get_topic(int,int){return &topic;}void on_forum_topic_changed(int,Topic*){updates++;}void read_forum_topic_messages(int,int,int,const vector<int>&);};
#define CHECK(x) if(!(x))throw std::runtime_error("check")
#define LOG(x) std::ostringstream()
METHOD
int main(){Td td;ForumTopicManager manager{&td};
 manager.read_forum_topic_messages(1,5,140,{90,110,120,140});
 if(td.query.sent||manager.topic.topic_->read!=140||manager.topic.topic_->count!=8||manager.updates!=1)throw std::runtime_error("Ghost read leaked or did not advance local state");
 manager.read_forum_topic_messages(1,5,140,{110,120,140});
 if(manager.updates!=1||manager.topic.topic_->count!=8)throw std::runtime_error("duplicate viewport changed count");
 td.options.ghost=false;manager.read_forum_topic_messages(1,5,150,{150});
 if(td.query.sent!=1||manager.topic.topic_->count!=7)throw std::runtime_error("normal read request changed");
}
'''.replace('METHOD',method.replace('last_read_inbox_message_id.get_prev_server_message_id()','last_read_inbox_message_id'))
        with tempfile.TemporaryDirectory(prefix='forum-read-privacy-') as tmp:
            p=Path(tmp);(p/'test.cpp').write_text(source)
            subprocess.run(['g++','-std=c++17',str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True,text=True)
            subprocess.run([str(p/'test')],check=True,capture_output=True,text=True)

    def run_native(self, negative=None):
        methods='\n'.join(block(self.native/'ForumTopic.cpp', s) for s in (
            'void ForumTopic::preserve_local_read(const ForumTopic &previous)', 'bool ForumTopic::read_inbox_messages(',
            'bool ForumTopic::update_last_read_inbox_message_id(',
            'vector<int64> ForumTopic::get_local_read_state(', 'void ForumTopic::preserve_local_read(const vector<int64>'))
        serial=''
        if negative=='merge':
            methods=methods.replace('if (previous.last_read_inbox_message_id_ <= last_read_inbox_message_id_) {','if (true) {')
        if negative=='count':
            methods=methods.replace('unread_count_ = max(0, unread_count_ - max(0, newly_read_count));','/* old native read kept its count */')
        if negative=='persistence':
            methods=methods.replace('return {1, last_read_inbox_message_id_.get(), unread_count_, server_last_read_inbox_message_id_.get(),\n          server_unread_count_, last_message_id_.get()};','return {};')
        with tempfile.TemporaryDirectory(prefix='forum-local-read-') as tmp:
            p=Path(tmp);(p/'test.cpp').write_text(PREAMBLE+'namespace td {\n'+methods+'\n}\n'+serial+MAIN)
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra',str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True,text=True)
            return subprocess.run([str(p/'test')],capture_output=True,text=True)

    def test_native_read_refresh_restart_and_new_messages(self):
        r=self.run_native();self.assertEqual(r.returncode,0,r.stderr);print(r.stdout.strip())
    def test_negative_server_snapshot_replaces_local_read(self):
        r=self.run_native('merge');self.assertNotEqual(r.returncode,0);self.assertIn('frontier regressed',r.stderr)
    def test_negative_read_never_decreases_count(self):
        r=self.run_native('count');self.assertNotEqual(r.returncode,0);self.assertIn('remaining unread',r.stderr)
    def test_negative_restart_loses_raw_server_baseline(self):
        r=self.run_native('persistence');self.assertNotEqual(r.returncode,0);self.assertIn('baseline lost',r.stderr)

if __name__=='__main__':unittest.main()
