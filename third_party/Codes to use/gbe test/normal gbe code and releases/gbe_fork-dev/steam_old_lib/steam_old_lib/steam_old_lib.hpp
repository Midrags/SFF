#pragma once


namespace sold {

using steamclient_loader_t = void* (bool load);

void set_steamclient_loader(steamclient_loader_t *loader);
void set_tid(unsigned long tid);

}
