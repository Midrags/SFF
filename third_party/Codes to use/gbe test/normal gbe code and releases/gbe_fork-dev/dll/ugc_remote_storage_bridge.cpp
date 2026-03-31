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

#include "dll/ugc_remote_storage_bridge.h"

  
Ugc_Remote_Storage_Bridge::Ugc_Remote_Storage_Bridge(class Settings *settings)
{
    this->settings = settings;

    // subscribe to all mods initially
    subscribed = settings->modSet();
}

Ugc_Remote_Storage_Bridge::~Ugc_Remote_Storage_Bridge()
{
    std::lock_guard lock(global_mutex);
    
    steam_ugc_queries.clear();
}

void Ugc_Remote_Storage_Bridge::add_ugc_query_result(UGCHandle_t file_handle, PublishedFileId_t fileid, bool handle_of_primary_file)
{
    std::lock_guard lock(global_mutex);

    steam_ugc_queries[file_handle].mod_id = fileid;
    steam_ugc_queries[file_handle].is_primary_file = handle_of_primary_file;
}

bool Ugc_Remote_Storage_Bridge::remove_ugc_query_result(UGCHandle_t file_handle)
{
    std::lock_guard lock(global_mutex);

    return !!steam_ugc_queries.erase(file_handle);
}

std::optional<Ugc_Remote_Storage_Bridge::QueryInfo> Ugc_Remote_Storage_Bridge::get_ugc_query_result(UGCHandle_t file_handle) const
{
    std::lock_guard lock(global_mutex);
    
    auto it = steam_ugc_queries.find(file_handle);
    if (steam_ugc_queries.end() == it) return std::nullopt;
    return it->second;
}

void Ugc_Remote_Storage_Bridge::add_subbed_mod(PublishedFileId_t id)
{
    subscribed.insert(id);
}

void Ugc_Remote_Storage_Bridge::remove_subbed_mod(PublishedFileId_t id)
{
    subscribed.erase(id);
}

size_t Ugc_Remote_Storage_Bridge::subbed_mods_count() const
{
    return subscribed.size();
}

bool Ugc_Remote_Storage_Bridge::has_subbed_mod(PublishedFileId_t id) const
{
    return !!subscribed.count(id);
}

std::set<PublishedFileId_t>::iterator Ugc_Remote_Storage_Bridge::subbed_mods_itr_begin() const
{
    return subscribed.begin();
}

std::set<PublishedFileId_t>::iterator Ugc_Remote_Storage_Bridge::subbed_mods_itr_end() const
{
    return subscribed.end();
}
