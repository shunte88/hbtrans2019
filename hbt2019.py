#!/usr/bin/python3

import os
import sys
import time
import glob
import time
from datetime import datetime
import logging
import subprocess
import socket
from pathlib import Path, PurePath
from pymediainfo import MediaInfo
from pushbullet import Pushbullet


def get_pushbullet():
    api_key = ''
    device = ''
    pb = None
    pb_config = os.getenv('HB_PUSHBULLET_CONFIG', None)
    if Path(pb_config).exists():
        import yaml
        with open(pb_config) as pbc:
            pbconf = yaml.safe_load(pbc)
            api_key = pbconf['auth']
            device = pbconf['device']

    if '' != api_key:
        try:
            pb = Pushbullet(api_key)
            if '' != device:
                pb = pb.get_device(device)
        except InvalidKeyError as err:
            logging.warning('Invalid PB key:', err)

    return pb


def push_note(note, pb=None):

    logging.info(note)
    global hostname
    # push bullet status
    if pb is not None:
        title = '%s::%s' % (hostname, note)
        pb.push_note(title, '')


def run_command(cmd, exc=0):

    logging.debug(cmd)
    if 1 == exc:
        try:
            rc = subprocess.run(cmd, shell=True)
            if 0 == rc.returncode:
                return True
        except subprocess.CalledProcessError as err:
            logger.warning(err.output)
            return False
    return False


def is_on_mount(path):
    while True:
        if path == os.path.dirname(path):
            # we've hit the root dir
            return False
        elif os.path.ismount(path):
            return True
        path = os.path.dirname(path)


def timedelta_fmt(delta):

    hours, remainder = divmod(delta.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)

    ret = ''
    if 0 != hours:
        ret = '%d hours' % hours
    if 0 != minutes:
        minutes = '%d minutes' % minutes
        if '' != ret:
            ret += ', %s' % minutes
        else:
            ret = minutes
    if 0 != seconds:
        seconds = '%d seconds' % seconds
        if '' != ret:
            ret += ' and %s' % seconds
        else:
            ret = seconds

    return ret


def sizeof_fmt(num, suffix='B'):
    # all the way to yotta, just for fun!!!
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi', 'Yi']:
        if abs(num) < 1024.0:
            return "%3.2f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def pluralize(i):
    if 1 == i:
        return ''
    else:
        return 's'


def unique_target(archive, basefolder, basefile):
    uindex = 1

    folder = '%s/%s' % (archive,
                        basefolder)
    Path(folder).mkdir(parents=True, exist_ok=True)

    filename = '%s/%s.mkv' % (folder,
                              basefile)
    while Path(filename).exists():
        filename = '%s/%s-%d.mkv' % (folder,
                                     basefile,
                                     uindex)
        uindex += 1

    return filename


def main():

    # get video files from [sub]\folders
    files = []
    for filename in glob.iglob(myth_video+'/*/*.mpeg', recursive=True):
        if (time.time() - os.path.getmtime(filename) >= window):
            files.append(filename)

    # if we have files process them
    if files:

        # instatiate pushbullet connection
        # if we've configured a device then
        # we get a device specific pb object
        pb = get_pushbullet()

        # process count
        today = 0

        # sort by file modified time
        # this assumes files transcoded as they were transmitted
        files = sorted(files, key=os.path.getmtime)

        for file in files:

            # check we're not beyond process our window
            # can be used to throttle when device is busy
            # or simply as an endo of day roll
            if datetime.now().hour >= cutoff:
                break

            pf = Path(file)
            folder = pf.parent

            # kludge to nibble off the extension from basename
            basefile = pf.stem
            process_file = str(PurePath.joinpath(folder, basefile))+'.mpeg'

            # lock file - parallel processing...
            lock_file = process_file+'.lck'
            lf = Path(lock_file)

            if lf.exists():
                # file being processed by another instance - skip
                logging.info(
                    'File "%s" process in flight, skipping' % process_file)
                continue
            else:
                # create the lockfile
                lf.touch()

            # define the title - assumes standardized naming
            title = basefile.replace('.', ' ').strip()
            chapter_file = '%s/%d.staging.csv' % (stage_dir, pidnum)
            cf = Path(chapter_file)

            if cf.exists():
                cf.unlink()

            # chapter stop file
            cf.write_text('1,%s' % title)

            basefolder = str(folder).replace(myth_video, '')

            # ensure unique archive name - for some programing this is critical
            archive_file = unique_target(archive, basefolder, basefile)
            af = Path(archive_file)

            # PITA NAS post power outage!!!
            af.touch(mode=0o777, exist_ok=True)
            af.touch(mode=0o777, exist_ok=True)
            #####af.chmod(0o777)

            initsize = pf.stat().st_size
            track_height = 0
            track_width = 0

            media_info = MediaInfo.parse(file)
            for track in media_info.tracks:
                if 'Video' == track.track_type:
                    track_height = int(track.height)
                    track_width = int(track.width)

            preset = 'H.265 MKV 720p30'
            vwidth = '--width %d --height %d' % (track_width, track_height)
            if (1080 == track_height):
                vwidth = '--width 1280'
            elif (480 == track_height):
                preset = 'H.265 MKV 480p30'

            muxcmd = 'nice -n19 %s ' % handbrake
            muxcmd += '-i "%s" -o "%s" ' % (process_file, archive_file)
            muxcmd += '--preset="%s" -f mkv ' % preset

            # chapter file - test is redundant but safe
            if cf.exists():
                muxcmd += '--markers="%s" ' % chapter_file

            muxcmd += ' 2> /dev/null '

            inittime = datetime.now()

            status = 'Transcode Processing "%s"' % title

            push_note(status, pb)

            if run_command(muxcmd, 1):

                if af.exists():

                    tagcmd = 'mkvpropedit "%s" --edit info ' % archive_file
                    tagcmd += '--set "title=%s" 2> /dev/null' % title

                    # don't need return on the title setting
                    run_command(tagcmd, 1)

                    endtime = datetime.now()
                    archsize = af.stat().st_size

                    delta = endtime-inittime
                    dt = timedelta_fmt(delta)
                    saved = ((initsize-archsize)/initsize) * 100
                    today += 1

                    status = 'Processed "%s"\n' % title
                    status += 'Elapsed %s\n' % dt
                    status += 'Using preset: "%s"\n' % preset
                    status += 'File size saving:\n'
                    status += '%s to' % sizeof_fmt(initsize)
                    status += ' %s, ' % sizeof_fmt(archsize)
                    status += '%.3f%%\n' % saved
                    status += 'Processed %d file%s today' % (today,
                                                             pluralize(today))

                    push_note(status, pb)

                    # cleanup work files and the processed video
                    pf.unlink()

            if lf.exists():
                lf.unlink()
            if cf.exists():
                cf.unlink()

            # cleanup empty folders
            '''
            try:
                folder.rmdir()
                logging.debug('Cleanup empty folder', folder.name)
            except:
                pass
            '''

        logging.debug('Done.')

    else:
        logging.debug('No files to process')


stage_dir = '/tmp/'
NAS_dir = os.getenv('HB_NAS_BASE_FOLDER', None)
pidnum = os.getpid()
hostname = socket.gethostname()

# dir provided may not be the true mount but a subdir thereof
if is_on_mount(NAS_dir):
    archive = NAS_dir+'/video/tv'
else:
    print('NAS does not appear to be mounted at', NAS_dir)
    sys.exit(1)

# look for files older than specified window
# needs, at minimum, validation around the base folders
handbrake = os.getenv('HB_EXECUTABLE', '/usr/bin/HandBrakeCLI')
window = int(os.getenv('HB_PROCESS_WINDOW', (4 * 60 * 60)))
myth_video = os.getenv('HB_MYTH_BASE_LOCAL_FOLDER', None)
cutoff = int(os.getenv('HB_CUTOFF_HOUR', 22))
log_file = '/tmp/transcode.pylarge.log'

if __name__ == "__main__":

    log_format = '%(asctime)s %(levelname)-8s %(message)s'
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter(log_format)
    console.setFormatter(formatter)
    logging.basicConfig(level=logging.DEBUG,
                        format=log_format,
                        datefmt='%m-%d-%y %H:%M',
                        filename=log_file,
                        filemode='a')

    logging.getLogger('').addHandler(console)

    main()

sys.exit(0)
