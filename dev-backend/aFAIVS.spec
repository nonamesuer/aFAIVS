# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['main.py'],
             pathex=['C:\\Users\\LAI8PK\\Desktop\\Projects\\aFAIVS\\dev-backend'],
             binaries=[],
             datas=[
                ('C:\\Users\\LAI8PK\\Desktop\\Projects\\aFAIVS\\dev-frontend\\dist','static\\dist'),
                ('C:\\Users\\LAI8PK\\Desktop\\Projects\\aFAIVS\\dev-frontend\\out\\afaivs-win32-x64','static\\afaivs-win32-x64'),
                ],
             hiddenimports=[],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts, 
          [],
          exclude_binaries=True,
          name='aFAIVS',
          debug=True,
          bootloader_ignore_signals=False,
          strip=False,
          icon = 'C:\\Users\\LAI8PK\\Desktop\\Projects\\aFAIVS\\dev-backend\\aFAIVS.ico',
          upx=True,
          console=True,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None,
          version='version.txt' )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas, 
               strip=False,
               upx=True,
               upx_exclude=[],
               name='AI VISION EXPAND')