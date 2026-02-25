#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API
#endif

#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio_io.h"
#define TSF_IMPLEMENTATION
#include "tsf.h"
#define TML_IMPLEMENTATION
#include "tml.h"

typedef struct
{
    ma_device device;
    tsf *soundfont;
    tml_message *midi_head;
    tml_message *midi_current;
    double msec_time;
    int channel_active[16];    // State for each channel (1=on, 0=off)
    int channel_has_notes[16]; // Tracks if a channel is used by the MIDI
} MidiPlayer;

static MidiPlayer *g_Player = NULL;

static void AudioCallback(ma_device *pDevice, void *pOutput, const void *pInput, ma_uint32 frameCount)
{
    if (!g_Player || !g_Player->soundfont)
        return;

    int SampleBlock, SamplesToRender = frameCount;
    float *stream = (float *)pOutput;
    while (SamplesToRender > 0)
    {
        SampleBlock = (SamplesToRender > TSF_RENDER_EFFECTSAMPLEBLOCK ? TSF_RENDER_EFFECTSAMPLEBLOCK : SamplesToRender);

        // Process all MIDI messages that fall within this time block
        for (g_Player->msec_time += SampleBlock * (1000.0 / 44100.0);
             g_Player->midi_current && g_Player->msec_time >= g_Player->midi_current->time;
             g_Player->midi_current = g_Player->midi_current->next)
        {
            tml_message *msg = g_Player->midi_current;

            switch (msg->type)
            {
            // NOTE: tsf doesn't have support for TML_KEY_PRESSURR and TML_CHANNEL_PRESSURE

            // Sets the instrument.
            case TML_PROGRAM_CHANGE:
                boolean is_drums = msg->channel == 9;
                tsf_channel_set_presetnumber(g_Player->soundfont, msg->channel, msg->program, is_drums);
                break;

            // Channel-specific
            case TML_NOTE_ON:
                // Normalize to range (-1 to 1)
                float velocity = msg->velocity / 127.0f;
                if (g_Player->channel_active[msg->channel])
                    tsf_channel_note_on(g_Player->soundfont, msg->channel, msg->key, velocity);
                break;
            case TML_NOTE_OFF:
                if (g_Player->channel_active[msg->channel])
                    tsf_channel_note_off(g_Player->soundfont, msg->channel, msg->key);
                break;
            case TML_PITCH_BEND:
                if (g_Player->channel_active[msg->channel])
                    tsf_channel_set_pitchwheel(g_Player->soundfont, msg->channel, msg->pitch_bend);
                break;
            case TML_CONTROL_CHANGE:
                if (g_Player->channel_active[msg->channel])
                    tsf_channel_midi_control(g_Player->soundfont, msg->channel, msg->control, msg->control_value);
                break;
            }
        }

        tsf_render_float(g_Player->soundfont, stream, SampleBlock, 0);
        stream += SampleBlock * 2;
        SamplesToRender -= SampleBlock;
        if (g_Player->midi_current == NULL)
        {
            tsf_reset(g_Player->soundfont);
            g_Player->msec_time = 0.0;
            g_Player->midi_current = g_Player->midi_head;
        }
    }
}

API int StartPlayback(const char *midi_filename, const char *soundfont_filename, const int *initial_channel_states)
{
    if (g_Player)
        return -1;
    g_Player = (MidiPlayer *)malloc(sizeof(MidiPlayer));
    if (!g_Player)
        return 1;
    memset(g_Player, 0, sizeof(MidiPlayer));

    // Copy the initial state provided by Python
    if (initial_channel_states)
    {
        memcpy(g_Player->channel_active, initial_channel_states, 16 * sizeof(int));
    }
    else
    {
        // Fallback in case a NULL pointer is passed
        for (int i = 0; i < 16; i++)
            g_Player->channel_active[i] = 1;
    }

    g_Player->midi_head = tml_load_filename(midi_filename);
    if (!g_Player->midi_head)
    {
        free(g_Player);
        g_Player = NULL;
        return 2;
    }
    g_Player->midi_current = g_Player->midi_head;

    for (tml_message *m = g_Player->midi_head; m != NULL; m = m->next)
    {
        if (m->type == TML_NOTE_ON)
            g_Player->channel_has_notes[m->channel] = 1;
    }

    g_Player->soundfont = tsf_load_filename(soundfont_filename);
    if (!g_Player->soundfont)
    {
        tml_free(g_Player->midi_head);
        free(g_Player);
        g_Player = NULL;
        return 3;
    }

    ma_device_config deviceConfig = ma_device_config_init(ma_device_type_playback);
    deviceConfig.playback.format = ma_format_f32;
    deviceConfig.playback.channels = 2;
    deviceConfig.sampleRate = 44100;
    deviceConfig.dataCallback = AudioCallback;

    if (ma_device_init(NULL, &deviceConfig, &g_Player->device) != MA_SUCCESS)
    {
    }
    tsf_set_output(g_Player->soundfont, TSF_STEREO_INTERLEAVED, (int)deviceConfig.sampleRate, 0.0f);
    if (ma_device_start(&g_Player->device) != MA_SUCCESS)
    {
    }
    return 0;
}

API void StopPlayback()
{
    if (!g_Player)
        return;
    ma_device_uninit(&g_Player->device);
    tsf_close(g_Player->soundfont);
    tml_free(g_Player->midi_head);
    free(g_Player);
    g_Player = NULL;
}

// Mute or unmute a channel
API void ToggleChannel(int channel, int active)
{
    if (!g_Player || channel < 0 || channel >= 16)
        return;
    g_Player->channel_active[channel] = active;
    // If we are muting the channel, immediately stop all notes on it.
    if (!active)
        tsf_channel_note_off_all(g_Player->soundfont, channel);
}

// Get the list of channels that the MIDI file uses
API void GetUsedChannels(int *used_channels_array)
{
    if (!g_Player || !used_channels_array)
        return;
    memcpy(used_channels_array, g_Player->channel_has_notes, 16 * sizeof(int));
}