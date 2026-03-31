/* Copyright (C) 2019 Mr Goldberg
   This file is part of the Goldberg Emulator

   The Goldberg Emulator is free software; you can redistribute it and/or
   modify it under the terms of the GNU Lesser General Public
   License as published by the Free Software Foundation; either
   version 3 of the License, or (at your option) any later version.

   The Goldberg Emulator is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   Lesser General Public License for more details.

   You should have received a copy of the GNU Lesser General Public
   License along with the Goldberg Emulator; if not, see
   <http://www.gnu.org/licenses/>.  */

#include "dll/steam_game_coordinator.h"
#include "dll/dll.h"

constexpr int GC_MIN_VERSION = 20091217;
constexpr int GC_MAX_VERSION = 20110413;

#pragma pack( push, 1 )
//-----------------------------------------------------------------------------
// Purpose: Header for messages from a client or gameserver to or from the GC
//-----------------------------------------------------------------------------
struct GCMsgHdr_t
{
    uint32  m_eMsg;                     // The message type
    uint64  m_ulSteamID;                // User's SteamID
};

//-----------------------------------------------------------------------------
// Purpose: Header for messages from a client or gameserver to or from the GC
//          That contains source and destination jobs for the purpose of
//          replying messages.
//-----------------------------------------------------------------------------
struct GCMsgHdrEx_t
{
    uint32  m_eMsg;                     // The message type
    uint64  m_ulSteamID;                // User's SteamID
    uint16  m_nHdrVersion;
    JobID_t m_JobIDTarget;
    JobID_t m_JobIDSource;
};

struct ProtoBufMsgHeader_t
{
    uint32          m_EMsgFlagged;          // High bit should be set to indicate this message header type is in use.  The rest of the bits indicate message type.
    uint32          m_cubProtoBufExtHdr;    // Size of the extended header which is a serialized protobuf object.  Indicates where it ends and the serialized body protobuf begins.
};
#pragma pack(pop)

template <class T>
static void ser_var(std::string &buf, const T &input)
{
    buf.append(reinterpret_cast<const char *>(&input), sizeof(T));
}

static void ser_varstring(std::string &buf, const std::string &input)
{
    uint16 len = static_cast<uint16>(input.size());
    if (len != 0) {
        ser_var<uint16>(buf, len + 1);
        buf.append(input);
        buf.push_back('\0');
    } else {
        ser_var<uint16>(buf, 0);
    }
}

template <class T>
static T deser_var(const char *&p) {
    T output;
    memcpy(&output, p, sizeof(T));
    p += sizeof(T);
    return output;
}

bool Steam_Game_Coordinator::gc_enabled()
{
    return (gc_version >= GC_MIN_VERSION && gc_version <= GC_MAX_VERSION);
}

Steam_User_Items *Steam_Game_Coordinator::client_items()
{
    return get_steam_client()->steam_user_items;
}

Steam_GameServer_Items *Steam_Game_Coordinator::server_items()
{
    return get_steam_client()->steam_gameserver_items;;
}

void Steam_Game_Coordinator::parse_gc_config()
{
    std::string file_path = Local_Storage::get_game_settings_path() + gc_config_file;
    nlohmann::json gc_json;
    if (!local_storage->load_json(file_path, gc_json))
        return;

    try {
        gc_version = gc_json.value("gc_version", 0);
    } catch (std::exception &e) {
        const char *errorMessage = e.what();
        PRINT_DEBUG("error parsing GC config: %s", errorMessage);
        gc_version = 0;
    }
}

void Steam_Game_Coordinator::push_incoming(uint32 msg_type, const std::string &message, double delay)
{
    PRINT_DEBUG("%u %.2f", msg_type, delay);

    GC_Message new_item;
    new_item.msg_type = msg_type;
    new_item.msg_body = message;
    new_item.created = std::chrono::high_resolution_clock::now();
    new_item.post_in = delay;
    pending_messages.push_back(new_item);
}

std::string Steam_Game_Coordinator::build_msg_header(JobID_t target_job, JobID_t source_job)
{
    std::string message;
    GCMsgHdrEx_t hdr{};
    hdr.m_nHdrVersion = 1;
    hdr.m_JobIDTarget = target_job;
    hdr.m_JobIDSource = source_job;
    ser_var<GCMsgHdrEx_t>(message, hdr);
    return message.substr(sizeof(GCMsgHdr_t));
}

GCMsgHdrEx_t Steam_Game_Coordinator::parse_msg_header(const char *&p)
{
    size_t write_offset = sizeof(GCMsgHdr_t);
    size_t hdr_size = sizeof(GCMsgHdrEx_t) - write_offset;
    GCMsgHdrEx_t hdr{};
    memcpy(reinterpret_cast<char *>(&hdr) + write_offset, p, hdr_size);
    p += hdr_size;
    return hdr;
}

uint64 Steam_Game_Coordinator::item_id_local_to_network(uint64 item_id)
{
    if (item_id == 0)
        return 0;

    // Add SteamID to item ID to avoid ID collisions in multiplayer games.
    uint32 account_id = settings->get_local_steam_id().GetAccountID();

    if (settings->use_32bit_inventory_item_ids) {
        // 32-bit mode
        item_id <<= 20ull;
        item_id |= static_cast<uint64>(account_id) & 0x000FFFFFull;
    } else {
        // 64-bit mode
        item_id <<= 32ull;
        item_id |= static_cast<uint64>(account_id);
    }

    return item_id;
}

uint64 Steam_Game_Coordinator::item_id_network_to_local(uint64 item_id)
{
    if (settings->use_32bit_inventory_item_ids) {
        // 32-bit mode
        item_id >>= 20ull;
    } else {
        // 64-bit mode
        item_id >>= 32ull;
    }

    return item_id;
}

void Steam_Game_Coordinator::handle_set_item_pos(const void *input, uint32 input_size)
{
    if (is_server || input_size < 30)
        return;

    const char *p = reinterpret_cast<const char *>(input);
    GCMsgHdrEx_t hdr = parse_msg_header(p);
    uint64 item_id = deser_var<uint64>(p);
    uint32 inv_pos = deser_var<uint32>(p);

    if (const Econ_Item *item = set_item_pos(item_id, inv_pos, true)) {
        on_item_pos_updated(settings->get_local_steam_id(), *item);
    }
}

void Steam_Game_Coordinator::handle_delete_item(const void *input, uint32 input_size)
{
    if (is_server || input_size < 26)
        return;

    const char *p = reinterpret_cast<const char *>(input);
    GCMsgHdrEx_t hdr = parse_msg_header(p);
    uint64 item_id = deser_var<uint64>(p);

    if (delete_item(item_id, true)) {
        on_item_deleted(settings->get_local_steam_id(), item_id);
    }
}

void Steam_Game_Coordinator::handle_respawn(const void *input, uint32 input_size)
{
    if (is_server || input_size < 19)
        return;

    auto gameserver_items_msg = new GameServer_Items_Messages();
    gameserver_items_msg->set_type(GameServer_Items_Messages::Request_Respawn);
    gameserver_items_msg->set_is_gc(true);

    Common_Message msg{};
    msg.set_allocated_gameserver_items_messages(gameserver_items_msg);
    msg.set_source_id(settings->get_local_steam_id().ConvertToUint64());
    network->sendToAllGameservers(&msg, true);
}

void Steam_Game_Coordinator::handle_motd_request(const void *input, uint32 input_size)
{
    if (is_server || input_size < 24)
        return;

    const char *p = reinterpret_cast<const char *>(input);
    GCMsgHdrEx_t hdr = parse_msg_header(p);
    uint32 last_req_time = deser_var<uint32>(p);
    uint16 language = deser_var<uint16>(p);

    // k_EMsgGCMOTDRequestResponse
    uint32 msg_type = 1013;
    std::string message = build_msg_header();
    uint16 num_entries = 0;
    ser_var<uint16>(message, num_entries);

    push_incoming(msg_type, message);
}

void Steam_Game_Coordinator::steam_network_callback(void *object, Common_Message *msg)
{
    //PRINT_DEBUG_ENTRY();

    auto inst = (Steam_Game_Coordinator *)object;
    inst->network_callback(msg);
}

void Steam_Game_Coordinator::steam_run_every_runcb(void *object)
{
    // PRINT_DEBUG_ENTRY();

    Steam_Game_Coordinator *steam_gamecoordinator = (Steam_Game_Coordinator *)object;
    steam_gamecoordinator->RunCallbacks();
}

Steam_Game_Coordinator::Steam_Game_Coordinator(class Settings *settings, class Networking *network, class Local_Storage *local_storage, class SteamCallBacks *callbacks, class RunEveryRunCB *run_every_runcb, bool is_server)
{
    this->settings = settings;
    this->network = network;
    this->local_storage = local_storage;
    this->callbacks = callbacks;
    this->run_every_runcb = run_every_runcb;
    this->is_server = is_server;

    this->network->setCallback(CALLBACK_ID_GAMESERVER_ITEMS, settings->get_local_steam_id(), &Steam_Game_Coordinator::steam_network_callback, this);
    this->network->setCallback(CALLBACK_ID_USER_STATUS, settings->get_local_steam_id(), &Steam_Game_Coordinator::steam_network_callback, this);
    this->run_every_runcb->add(&Steam_Game_Coordinator::steam_run_every_runcb, this);

    parse_gc_config();
}

Steam_Game_Coordinator::~Steam_Game_Coordinator()
{
    this->network->rmCallback(CALLBACK_ID_GAMESERVER_ITEMS, settings->get_local_steam_id(), &Steam_Game_Coordinator::steam_network_callback, this);
    this->network->rmCallback(CALLBACK_ID_USER_STATUS, settings->get_local_steam_id(), &Steam_Game_Coordinator::steam_network_callback, this);
    this->run_every_runcb->remove(&Steam_Game_Coordinator::steam_run_every_runcb, this);
}

void Steam_Game_Coordinator::initialize_gc()
{
    if (!gc_enabled() || gc_initialized)
        return;

    gc_initialized = true;

    // Servers don't need anything.
    if (is_server)
        return;

    // Load user's items.
    const auto &items = load_items_from_file();
    on_items_received(settings->get_local_steam_id(), items);

    // HACK: Put any messages from the initialization directly into the queue so that the initial
    // IsMessageAvailable call reads it.
    for (const GC_Message &msg : pending_messages) {
        incoming_messages.push(msg);

        GCMessageAvailable_t data{};
        data.m_nMessageSize = static_cast<uint32>(msg.msg_body.size());
        callbacks->addCBResult(data.k_iCallback, &data, sizeof(data));
    }
    pending_messages.clear();
}

const std::vector<Econ_Item> &Steam_Game_Coordinator::load_items_from_file()
{
    if (items_loaded)
        return items;

    items_loaded = true;

    nlohmann::json items_json;
    if (!local_storage->load_json_file("", items_user_file, items_json))
        return items;

    for (auto it = items_json.begin(); it != items_json.end(); it++) {
        Econ_Item new_item{};
        try {
            new_item.id = std::stoull(it.key());
        } catch (...) {
            continue;
        }
        if (new_item.id == 0)
            continue;

        try {
            new_item.def = it->value("definition", 0u); // 0 is a valid item definition
            new_item.level = it->value("level", 1u);
            new_item.quality = static_cast<EItemQuality>(it->value("quality", 0));
            new_item.inv_pos = it->value("inventory_pos", 0u);
            new_item.quantity = it->value("quantity", 1u);
            new_item.flags = it->value("flags", 0u);
            new_item.origin = it->value("origin", 0u);
            new_item.custom_name = it->value("custom_name", std::string());
            new_item.custom_desc = it->value("custom_desc", std::string());
            new_item.original_id = it->value("original_id", 0ull);
            new_item.in_use = false;

            if (it->contains("attributes")) {
                for (const auto &attr : it->at("attributes")) {
                    Econ_Item_Attribute new_attr{};
                    new_attr.def = attr.value("definition", 0u);
                    new_attr.value = attr.value("value", 0.0f);
                    if (new_attr.def == 0) // 0 is not a valid attribute definition, however
                        continue;

                    new_item.attributes.push_back(new_attr);
                }
            }
        } catch (std::exception &e) {
            const char *errorMessage = e.what();
            PRINT_DEBUG("error parsing item %llu: %s", new_item.id, errorMessage);
            continue;
        }

        new_item.id = item_id_local_to_network(new_item.id);
        new_item.original_id = item_id_local_to_network(new_item.original_id);

        // Check custom name and custom description limits.
        if (!check_econ_item_name(new_item.custom_name)) {
            new_item.custom_name.clear();
        }

        if (!check_econ_item_desc(new_item.custom_desc)) {
            new_item.custom_desc.clear();
        }

        items.push_back(new_item);
    }

    return items;
}

void Steam_Game_Coordinator::save_items_to_file()
{
    nlohmann::json items_json;

    for (const Econ_Item &item : items) {
        uint64 item_id = item_id_network_to_local(item.id);

        nlohmann::json json_item;
        json_item["definition"] = item.def;
        json_item["level"] = item.level;
        json_item["quality"] = item.quality;
        json_item["inventory_pos"] = item.inv_pos;
        json_item["quantity"] = item.quantity;
        json_item["flags"] = item.flags;
        json_item["origin"] = item.origin;
        json_item["custom_name"] = item.custom_name;
        json_item["custom_desc"] = item.custom_desc;
        json_item["original_id"] = item_id_network_to_local(item.original_id);

        for (const Econ_Item_Attribute &attr : item.attributes) {
            nlohmann::json json_attr;
            json_attr["definition"] = attr.def;
            json_attr["value"] = attr.value;
            json_item["attributes"].push_back(json_attr);
        }

        items_json[std::to_string(item_id)] = json_item;
    }

    local_storage->write_json_file("", items_user_file, items_json);
}

const Econ_Item *Steam_Game_Coordinator::set_item_pos(uint64 item_id, uint32 inv_pos, bool is_gc)
{
    for (Econ_Item &item : items) {
        if (item.id != item_id)
            continue;

        item.inv_pos = inv_pos;
        save_items_to_file();

        // Let the others know, too.
        auto inventory_msg = new GameServer_Items_Messages::InventoryPosUpdate();
        inventory_msg->set_item_id(item_id);
        inventory_msg->set_item_inv_pos(inv_pos);

        auto gameserver_items_msg = new GameServer_Items_Messages();
        gameserver_items_msg->set_type(GameServer_Items_Messages::Request_UpdateInventoryPos);
        gameserver_items_msg->set_is_gc(is_gc);
        gameserver_items_msg->set_allocated_inventory_pos_update(inventory_msg);

        Common_Message msg{};
        msg.set_allocated_gameserver_items_messages(gameserver_items_msg);
        msg.set_source_id(settings->get_local_steam_id().ConvertToUint64());
        network->sendToAll(&msg, true);

        return &item;
    }

    return nullptr;
}

bool Steam_Game_Coordinator::delete_item(uint64 item_id, bool is_gc)
{
    for (auto it = items.begin(); it != items.end(); it++) {
        if (it->id != item_id)
            continue;

        items.erase(it);
        save_items_to_file();

        // Let the others know, too.
        auto drop_msg = new GameServer_Items_Messages::ItemDeletion();
        drop_msg->set_item_id(item_id);

        auto gameserver_items_msg = new GameServer_Items_Messages();
        gameserver_items_msg->set_type(GameServer_Items_Messages::Request_DeleteItem);
        gameserver_items_msg->set_is_gc(is_gc);
        gameserver_items_msg->set_allocated_item_deletion(drop_msg);

        Common_Message msg{};
        msg.set_allocated_gameserver_items_messages(gameserver_items_msg);
        msg.set_source_id(settings->get_local_steam_id().ConvertToUint64());
        network->sendToAll(&msg, true);

        return true;
    }

    return false;
}

void Steam_Game_Coordinator::request_user_items(CSteamID steam_id, SteamAPICall_t api_call, bool is_gc)
{
    RequestInventory new_request{};
    new_request.created = std::chrono::high_resolution_clock::now();
    new_request.steam_id = steam_id;
    new_request.steam_api_call = api_call;
    new_request.is_gc = is_gc;
    pending_items_requests.push_back(new_request);

    auto request_msg = new GameServer_Items_Messages::InventoryRequest();
    request_msg->set_steam_api_call(new_request.steam_api_call);

    auto gameserver_items_msg = new GameServer_Items_Messages();
    gameserver_items_msg->set_type(GameServer_Items_Messages::Request_Inventory);
    gameserver_items_msg->set_is_gc(is_gc);
    gameserver_items_msg->set_allocated_inventory_request(request_msg);

    Common_Message msg{};
    msg.set_allocated_gameserver_items_messages(gameserver_items_msg);
    msg.set_source_id(settings->get_local_steam_id().ConvertToUint64());
    msg.set_dest_id(steam_id.ConvertToUint64());
    network->sendTo(&msg, true);
}

SteamAPICall_t Steam_Game_Coordinator::find_items_request(CSteamID steam_id)
{
    auto it = std::find_if(
        pending_items_requests.begin(), pending_items_requests.end(),
        [=](const RequestInventory &item) {
            return item.steam_id == steam_id;
        }
    );

    if (it == pending_items_requests.end())
        return k_uAPICallInvalid;

    return it->steam_api_call;
}

void Steam_Game_Coordinator::remove_user_items(CSteamID steam_id)
{
    all_user_items.erase(steam_id);

    // Clean up any pending requests we have.
    for (auto it = pending_items_requests.begin(); it != pending_items_requests.end();) {
        if (it->steam_id == steam_id) {
            it = pending_items_requests.erase(it);
        } else {
            it++;
        }
    }

    if (gc_initialized) {
        // k_ESOMsg_CacheUnsubscribed
        uint32 msg_type = 25;
        std::string message = build_msg_header();
        ser_var<uint64>(message, steam_id.ConvertToUint64());

        push_incoming(msg_type, message);
    }
}

void Steam_Game_Coordinator::on_client_connected(CSteamID steam_id)
{
    if (!steam_id.BIndividualAccount())
        return;

    if (gc_initialized) {
        request_user_items(steam_id, generate_steam_api_call_id(), true);
    }
}

void Steam_Game_Coordinator::on_client_disconnected(CSteamID steam_id)
{
    if (!steam_id.BIndividualAccount())
        return;

    remove_user_items(steam_id);
}

void Steam_Game_Coordinator::on_items_received(CSteamID steam_id, const std::vector<Econ_Item> &items)
{
    if (!gc_initialized)
        return;

    // k_ESOMsg_CacheSubscribed
    uint32 msg_type = 24;
    std::string message = build_msg_header();

    uint64 owner_id = steam_id.ConvertToUint64();
    uint16 num_types = 1;

    ser_var<uint64>(message, owner_id);
    ser_var<uint16>(message, num_types);

    // econ items (1)
    uint32 object_type = 1;
    uint16 num_items = static_cast<uint16>(items.size());

    ser_var<uint32>(message, object_type);
    ser_var<uint16>(message, num_items);

    for (const Econ_Item &item : items) {
        ser_var<uint64>(message, item.id);
        ser_var<uint32>(message, steam_id.GetAccountID());
        ser_var<uint16>(message, item.def);
        ser_var<uint8>(message, item.level);
        ser_var<uint8>(message, item.quality);
        ser_var<uint32>(message, item.inv_pos);
        ser_var<uint32>(message, item.quantity);

        if (gc_version >= 20100428) {
            // Strings are passed as UTF-8 which is good for us since we can just copy std::string as is.
            ser_varstring(message, item.custom_name);

            if (gc_version >= 20100930) {
                ser_var<uint8>(message, item.flags);

                if (gc_version >= 20101027) {
                    ser_var<uint8>(message, item.origin);
                    ser_varstring(message, item.custom_desc);
                    ser_var<bool>(message, item.in_use);
                }
            }
        }

        ser_var<uint16>(message, static_cast<uint16>(item.attributes.size()));

        for (const Econ_Item_Attribute &attr : item.attributes) {
            ser_var<uint16>(message, attr.def);
            ser_var<float>(message, attr.value);
        }

        if (gc_version >= 20101217) {
            ser_var<uint64>(message, item.original_id);
        }
    }

    push_incoming(msg_type, message);
}

void Steam_Game_Coordinator::on_item_pos_updated(CSteamID steam_id, const Econ_Item &item)
{
    if (!gc_initialized)
        return;

    // k_ESOMsg_Update
    uint32 msg_type = 22;
    std::string message = build_msg_header();

    uint64 owner_id = steam_id.ConvertToUint64();
    uint32 object_type = 1;
    uint8 num_fields = 1;

    ser_var<uint64>(message, owner_id);
    ser_var<uint32>(message, object_type);
    ser_var<uint64>(message, item.id);
    ser_var<uint8>(message, num_fields);

    uint8 field_idx = 5;
    ser_var<uint8>(message, field_idx);
    ser_var<uint32>(message, item.inv_pos);

    if (gc_version >= 20101027) {
        ser_var<bool>(message, item.in_use);
    }

    push_incoming(msg_type, message);
}

void Steam_Game_Coordinator::on_item_deleted(CSteamID steam_id, uint64 item_id)
{
    if (!gc_initialized)
        return;

    // k_ESOMsg_Destroy
    uint32 msg_type = 23;
    std::string message = build_msg_header();

    uint64 owner_id = steam_id.ConvertToUint64();
    uint32 object_type = 1;

    ser_var<uint64>(message, owner_id);
    ser_var<uint32>(message, object_type);
    ser_var<uint64>(message, item_id);

    push_incoming(msg_type, message);
}

// sends a message to the Game Coordinator
EGCResults Steam_Game_Coordinator::SendMessage_( uint32 unMsgType, const void *pubData, uint32 cubData )
{
    PRINT_DEBUG("0x%08X %u len %u", unMsgType, (~protobuf_mask) & unMsgType, cubData);
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    if (!gc_initialized)
        return k_EGCResultOK;

    switch (unMsgType) {
        case 1001:
            PRINT_DEBUG("k_EMsgGCSetSingleItemPosition");
            handle_set_item_pos(pubData, cubData);
            break;
        case 1004:
            PRINT_DEBUG("k_EMsgGCDelete");
            handle_delete_item(pubData, cubData);
            break;
        case 1012:
            PRINT_DEBUG("k_EMsgGCMOTDRequest");
            handle_motd_request(pubData, cubData);
            break;
        case 1029:
            PRINT_DEBUG("k_EMsgGCRespawnPostLoadoutChange");
            handle_respawn(pubData, cubData);
            break;
        default:
            break;
    }

    return k_EGCResultOK;
}

// returns true if there is a message waiting from the game coordinator
bool Steam_Game_Coordinator::IsMessageAvailable( uint32 *pcubMsgSize )
{
    PRINT_DEBUG_ENTRY();
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    if (!gc_initialized || incoming_messages.empty()) {
        *pcubMsgSize = 0;
        return false;
    }

    GC_Message &message = incoming_messages.front();
    *pcubMsgSize = static_cast<uint32>(message.msg_body.size());
    return true;
}

// fills the provided buffer with the first message in the queue and returns k_EGCResultOK or 
// returns k_EGCResultNoMessage if there is no message waiting. pcubMsgSize is filled with the message size.
// If the provided buffer is not large enough to fit the entire message, k_EGCResultBufferTooSmall is returned
// and the message remains at the head of the queue.
EGCResults Steam_Game_Coordinator::RetrieveMessage( uint32 *punMsgType, void *pubDest, uint32 cubDest, uint32 *pcubMsgSize )
{
    PRINT_DEBUG_ENTRY();
    std::lock_guard<std::recursive_mutex> lock(global_mutex);

    if (!gc_initialized || incoming_messages.empty()) {
        *pcubMsgSize = 0;
        return k_EGCResultNoMessage;
    }

    GC_Message &message = incoming_messages.front();

    uint32 outsize = static_cast<uint32>(message.msg_body.size());
    if (outsize > cubDest) {
        return k_EGCResultBufferTooSmall;
    }

    *punMsgType = message.msg_type;
    *pcubMsgSize = outsize;
    message.msg_body.copy(reinterpret_cast<char *>(pubDest), cubDest);

    incoming_messages.pop();
    return k_EGCResultOK;
}

// server requested our inventory
void Steam_Game_Coordinator::network_callback_inventory_request(Common_Message *msg)
{
    // Server instance should never receive this.
    if (is_server)
        return;

    uint64 server_steamid = msg->source_id();

    if (!msg->gameserver_items_messages().has_inventory_request()) {
        PRINT_DEBUG("error empty msg");
        return;
    }

    bool is_gc = msg->gameserver_items_messages().is_gc();
    const auto &request_msg = msg->gameserver_items_messages().inventory_request();
    auto response_msg = new GameServer_Items_Messages::InventoryResponse();
    response_msg->set_steam_api_call(request_msg.steam_api_call());

    for (const Econ_Item &item : items) {
        auto new_item = response_msg->add_items();
        new_item->set_id(item.id);
        new_item->set_def(item.def);
        new_item->set_level(item.level);
        new_item->set_quality(static_cast<int32>(item.quality));
        new_item->set_inv_pos(item.inv_pos);
        new_item->set_quantity(item.quantity);
        new_item->set_flags(item.flags);
        new_item->set_origin(item.origin);
        new_item->set_custom_name(item.custom_name);
        new_item->set_custom_desc(item.custom_desc);
        new_item->set_original_id(item.original_id);

        for (const auto &attr : item.attributes) {
            auto new_attr = new_item->add_attributes();
            new_attr->set_def(attr.def);
            new_attr->set_value(attr.value);
        }
    }

    auto gameserver_items_msg = new GameServer_Items_Messages();
    gameserver_items_msg->set_type(GameServer_Items_Messages::Response_Inventory);
    gameserver_items_msg->set_is_gc(is_gc);
    gameserver_items_msg->set_allocated_inventory_response(response_msg);

    Common_Message new_msg{};
    new_msg.set_allocated_gameserver_items_messages(gameserver_items_msg);
    new_msg.set_source_id(settings->get_local_steam_id().ConvertToUint64());
    new_msg.set_dest_id(server_steamid);
    network->sendTo(&new_msg, true);

    PRINT_DEBUG("server requested inventory, sent %u items", static_cast<uint32>(items.size()));
}

// user sent their inventory
void Steam_Game_Coordinator::network_callback_inventory_response(Common_Message *msg)
{
    uint64 user_steamid = msg->source_id();

    PRINT_DEBUG("player sent their inventory %llu", user_steamid);
    if (!msg->gameserver_items_messages().has_inventory_response()) {
        PRINT_DEBUG("error empty msg");
        return;
    }

    bool is_gc = msg->gameserver_items_messages().is_gc();
    const auto &response_msg = msg->gameserver_items_messages().inventory_response();
    SteamAPICall_t api_call = response_msg.steam_api_call();

    // Find this pending request.
    auto it = std::find_if(
        pending_items_requests.begin(), pending_items_requests.end(),
        [=](const RequestInventory &item) {
            return item.steam_api_call == response_msg.steam_api_call() &&
                item.steam_id == user_steamid;
        }
    );
    if (pending_items_requests.end() == it) {
        PRINT_DEBUG("error got player inventory but pending request timedout/removed (doesn't exist)");
        return;
    }
    pending_items_requests.erase(it);

    auto &items = all_user_items[user_steamid];
    items.clear();

    for (const auto &item : response_msg.items()) {
        Econ_Item new_item;
        new_item.id = item.id();
        new_item.def = item.def();
        new_item.level = item.level();
        new_item.quality = static_cast<EItemQuality>(item.quality());
        new_item.inv_pos = item.inv_pos();
        new_item.quantity = item.quantity();
        new_item.flags = item.flags();
        new_item.origin = item.origin();
        new_item.custom_name = item.custom_name();
        new_item.custom_desc = item.custom_desc();
        new_item.original_id = item.original_id();
        new_item.in_use = false;
        if (new_item.id == 0)
            continue;

        for (const auto &attr : item.attributes()) {
            Econ_Item_Attribute new_attr;
            new_attr.def = attr.def();
            new_attr.value = attr.value();
            if (new_attr.def == 0)
                continue;

            new_item.attributes.push_back(new_attr);
        }

        // Check custom name and custom description limits.
        if (!check_econ_item_name(new_item.custom_name)) {
            new_item.custom_name.clear();
        }

        if (!check_econ_item_desc(new_item.custom_desc)) {
            new_item.custom_desc.clear();
        }

        items.push_back(new_item);
    }

    if (is_gc) {
        on_items_received(user_steamid, items);
    } else {
        server_items()->on_items_received(user_steamid, items.size(), api_call, true);
    }

    PRINT_DEBUG("got player inventory: %u items", response_msg.items_size());
}

// user updated item inventory position
void Steam_Game_Coordinator::network_callback_inventory_pos_update(Common_Message *msg)
{
    uint64 user_steamid = msg->source_id();

    PRINT_DEBUG("player updated item inventory position %llu", user_steamid);
    if (!msg->gameserver_items_messages().has_inventory_pos_update()) {
        PRINT_DEBUG("error empty msg");
        return;
    }

    if (!all_user_items.count(user_steamid)) {
        PRINT_DEBUG("error no inventory for player", user_steamid);
        return;
    }

    bool is_gc = msg->gameserver_items_messages().is_gc();
    const auto &inventory_msg = msg->gameserver_items_messages().inventory_pos_update();
    uint64 item_id = inventory_msg.item_id();
    uint32 item_inv_pos = inventory_msg.item_inv_pos();

    auto &items = all_user_items.at(user_steamid);

    for (Econ_Item &item : items) {
        if (item.id != item_id)
            continue;

        item.inv_pos = item_inv_pos;

        if (is_gc) {
            on_item_pos_updated(user_steamid, item);
        } else {
            server_items()->on_item_pos_updated(user_steamid, item_id, item_inv_pos);
        }

        PRINT_DEBUG("got updated item inventory position: %llu 0x%08X", item_id, item_inv_pos);
        return;
    }

    PRINT_DEBUG("error item %llu not found", item_id);
}

// user deleted an item
void Steam_Game_Coordinator::network_callback_item_deletion(Common_Message *msg)
{
    uint64 user_steamid = msg->source_id();

    PRINT_DEBUG("player deleted inventory item %llu", user_steamid);
    if (!msg->gameserver_items_messages().has_item_deletion()) {
        PRINT_DEBUG("error empty msg");
        return;
    }

    if (!all_user_items.count(user_steamid)) {
        PRINT_DEBUG("error no inventory for player", user_steamid);
        return;
    }

    bool is_gc = msg->gameserver_items_messages().is_gc();
    const auto &drop_msg = msg->gameserver_items_messages().item_deletion();
    uint64 item_id = drop_msg.item_id();

    auto &items = all_user_items.at(user_steamid);

    for (auto it = items.begin(); it != items.end(); it++) {
        if (it->id != item_id)
            continue;

        items.erase(it);

        if (is_gc) {
            on_item_deleted(user_steamid, item_id);
        } else {
            server_items()->on_item_deleted(user_steamid, item_id);
        }

        PRINT_DEBUG("deleted player's inventory item: %llu", item_id);
        return;
    }

    PRINT_DEBUG("error item %llu not found", item_id);
}

// user wants to respawn after loadout change
void Steam_Game_Coordinator::network_callback_respawn_request(Common_Message *msg)
{
    if (!gc_initialized || !is_server)
        return;

    uint64 user_steamid = msg->source_id();
    if (!all_user_items.count(user_steamid))
        return;

    // k_EMsgGCRespawnPostLoadoutChange
    uint32 msg_type = 1029;
    std::string message = build_msg_header();
    ser_var<uint64>(message, user_steamid);

    push_incoming(msg_type, message);
}

// only triggered when we have a message
void Steam_Game_Coordinator::network_callback(Common_Message *msg)
{
    if (msg->source_id() == settings->get_local_steam_id().ConvertToUint64()) return;

    if (msg->has_gameserver_items_messages()) {
        switch (msg->gameserver_items_messages().type()) {
        // server requested our inventory
        case GameServer_Items_Messages::Request_Inventory:
            network_callback_inventory_request(msg);
        break;

        // user sent their inventory
        case GameServer_Items_Messages::Response_Inventory:
            network_callback_inventory_response(msg);
        break;

        // user updated item inventory position
        case GameServer_Items_Messages::Request_UpdateInventoryPos:
            network_callback_inventory_pos_update(msg);
        break;

        // user deleted an item
        case GameServer_Items_Messages::Request_DeleteItem:
            network_callback_item_deletion(msg);
        break;

        // user wants to respawn after loadout change
        case GameServer_Items_Messages::Request_Respawn:
            network_callback_respawn_request(msg);
        break;

        default:
            PRINT_DEBUG("unhandled type %i", (int)msg->gameserver_items_messages().type());
        break;
        }
    } else if (msg->has_low_level()) {
        if (!is_server && gc_initialized) {
            uint64 user_steamid = msg->source_id();

            // Client needs to know other players' inventories as well since the game uses them to
            // validate cosmetic items.
            switch (msg->low_level().type()) {
            case Low_Level::CONNECT:
                request_user_items(user_steamid, generate_steam_api_call_id(), true);
            break;

            case Low_Level::DISCONNECT:
                remove_user_items(user_steamid);
            break;
            }
        }
    }
}

void Steam_Game_Coordinator::RunCallbacks()
{
    for (auto it = pending_messages.begin(); it != pending_messages.end();) {
        if (check_timedout(it->created, it->post_in)) {
            incoming_messages.push(*it);

            GCMessageAvailable_t data{};
            data.m_nMessageSize = static_cast<uint32>(it->msg_body.size());
            callbacks->addCBResult(data.k_iCallback, &data, sizeof(data));

            it = pending_messages.erase(it);
        } else {
            it++;
        }
    }

    for (auto it = pending_items_requests.begin(); it != pending_items_requests.end();) {
        if (check_timedout(it->created, 7.0)) {
            if (!it->is_gc) {
                server_items()->on_items_received(it->steam_id, items.size(), it->steam_api_call, false);
            }

            PRINT_DEBUG("player inventory request timeout %llu", it->steam_id);
            it = pending_items_requests.erase(it);
        } else {
            it++;
        }
    }
}
