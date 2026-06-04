std_msgs/Header header
uint8 STATE_LOST=0
uint8 STATE_VISIBLE=1
uint8 STATE_VISIBLE_NO_DEPTH=2

string id
string parent_id
string object_type
string role
uint8 state
float32 confidence
float32 x
float32 y
float32 z
colt_msgs/Box2D bbox
