from discord.ext import commands
from utils.logger import setup_logger
from utils.helpers import is_allowed_channel_for_message
import asyncio
import re
import discord
from datetime import datetime, timedelta
import json
import os
import config

logger = setup_logger(__name__)

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.suggestions_file = "data/function.json"
        
        # Dictionary chứa các cụm từ trigger và response tương ứng
        # Bạn có thể thêm các cụm từ mới vào đây
        # Format: "cụm từ trigger": "nội dung reply"
        self.trigger_responses = {
            # Thêm các cụm từ của bạn vào đây
            # Ví dụ:
            # "hên": "https://cdn.discordapp.com/attachments/1439553447384060047/1469976267284807781/tiktok_wzezzz_7598912564403244296.mp4?ex=69899d94&is=69884c14&hm=8692cfa0d9ddc358df10daf57403601b4586f7c1c9f5a8b090fa2a9641cef5b9&=&format=mp4&quality=lossless",
            # "tài liệu ở": "https://discord.com/channels/1184348724999225355/1241629913883217950/1403485129392783402",
            # "tài liệu đâu": "https://discord.com/channels/1184348724999225355/1241629913883217950/1403485129392783402",
            # "bã mía": "https://cdn.discordapp.com/attachments/1439553447384060047/1472549600328941690/bamia.mp4?ex=6992fa2f&is=6991a8af&hm=35efacc08ad8ae492f81d0910776b92d02cf0285b4610da47ba1ac7de0b57fe5&",
            # "vũ à vũ11111": "https://cdn.discordapp.com/attachments/1439553447384060047/1472551479264018537/tiktok_video_1.mp4?ex=6992fbef&is=6991aa6f&hm=57ebecef25de55920e8ef02f34d6a112d2c3ba729d7b60b13e127f965d64c247&",
            # "ngọc anh à ngọc anh1111": "https://cdn.discordapp.com/attachments/1439553447384060047/1472551479264018537/tiktok_video_1.mp4?ex=6992fbef&is=6991aa6f&hm=57ebecef25de55920e8ef02f34d6a112d2c3ba729d7b60b13e127f965d64c247&",
            # "em đừng có chối": "https://cdn.discordapp.com/attachments/1439553447384060047/1472551479264018537/tiktok_video_1.mp4?ex=6992fbef&is=6991aa6f&hm=57ebecef25de55920e8ef02f34d6a112d2c3ba729d7b60b13e127f965d64c247&",
            # "thọ à thọ111": "https://cdn.discordapp.com/attachments/1439553447384060047/1472551479264018537/tiktok_video_1.mp4?ex=6992fbef&is=6991aa6f&hm=57ebecef25de55920e8ef02f34d6a112d2c3ba729d7b60b13e127f965d64c247&",
            #  "thọ à thọ111": "https://cdn.discordapp.com/attachments/1439553447384060047/1472551479264018537/tiktok_video_1.mp4?ex=6992fbef&is=6991aa6f&hm=57ebecef25de55920e8ef02f34d6a112d2c3ba729d7b60b13e127f965d64c247&",
            # "gay": "https://cdn.discordapp.com/attachments/1439553447384060047/1472910769019683009/tiktok_anthonyngofficial_7398826499190689067.mp4?ex=69944a8c&is=6992f90c&hm=7c18c940e85d3eb4630a4ba6cc11d0ae1e95e8266312cf560a5a450f613dfb52&",
            # "hù ai dợ": "https://cdn.discordapp.com/attachments/1439553447384060047/1474372623159787654/The_Forum_la_mot_cong_ty_thieu_liem_chinh.mp4?ex=69999c01&is=69984a81&hm=f86604e08c0b9efe0cf61849a277c090b477be7d162d2801a86eae13c4a7c3f2&",
            # "đi dọc việt nam": "https://cdn.discordapp.com/attachments/1439553447384060047/1473317705540178167/tiktok_mixigaming_7186510228207226117.mp4?ex=6995c589&is=69947409&hm=edcf3c7c4f0f34f506ca322293066dace1edab864c325135762c4b06c14150d0&",
            # "karaoke":"https://cdn.discordapp.com/attachments/1439553447384060047/1473317705540178167/tiktok_mixigaming_7186510228207226117.mp4?ex=6995c589&is=69947409&hm=edcf3c7c4f0f34f506ca322293066dace1edab864c325135762c4b06c14150d0&",
            "ai hỏi": "https://cdn.discordapp.com/attachments/1439553447384060047/1473319675168293066/image.png?ex=6995c75f&is=699475df&hm=4b02ad9a4d349b2eb99a73896dcfcba7e1615672c9a5a5c2d4596db89dac2728&",
            # "mu":"https://www.youtube.com/watch?v=Vx-Lp3J-W2Q&list=RDVx-Lp3J-W2Q&start_radio=1",
            # "manchester united":"https://www.youtube.com/watch?v=Vx-Lp3J-W2Q&list=RDVx-Lp3J-W2Q&start_radio=1",
            # "đời nghệ sĩ":"https://cdn.discordapp.com/attachments/1439553447384060047/1474357120911671396/Tran_Thanh_chia_se_ve_su_rieng_tu_khoc_nghen_chu_Hao_Quang_Ruc_Ro_tai_du_an_phim_cua_am_Vinh_Hung.mp4?ex=69998d91&is=69983c11&hm=0574c8bb45c6a72fdbfc8853368d5c5bec5291c426b3e4cdd9aae475791aba6d&",
            # "hào quang rực rỡ":"https://cdn.discordapp.com/attachments/1439553447384060047/1474357120911671396/Tran_Thanh_chia_se_ve_su_rieng_tu_khoc_nghen_chu_Hao_Quang_Ruc_Ro_tai_du_an_phim_cua_am_Vinh_Hung.mp4?ex=69998d91&is=69983c11&hm=0574c8bb45c6a72fdbfc8853368d5c5bec5291c426b3e4cdd9aae475791aba6d&",

            # "cười":"https://cdn.discordapp.com/attachments/1439553447384060047/1474359212891967570/dd7d50a7f28e347ac5cfdaefff140abbxin-loi-nhung-tran-thanh-khong-cuoi.png?ex=69998f84&is=69983e04&hm=d5b3cc47b436f135c975129b59b3aed9abf93f3bffd1e7f436f910c14587c433&",
            # "trấn thành":"https://cdn.discordapp.com/attachments/1439553447384060047/1474359212891967570/dd7d50a7f28e347ac5cfdaefff140abbxin-loi-nhung-tran-thanh-khong-cuoi.png?ex=69998f84&is=69983e04&hm=d5b3cc47b436f135c975129b59b3aed9abf93f3bffd1e7f436f910c14587c433&",
            # "như đồng ý đi như":"https://cdn.discordapp.com/attachments/1439553447384060047/1474410336600985821/noname.mp4?ex=6999bf21&is=69986da1&hm=0be496087aa001fe91c894d36ff2e0f250d5f23c613c3f8b457d244d8d5f916b&",
            # "đỗ trung hiếu":"https://media.discordapp.net/attachments/1446865411814588426/1474411361114001461/IMG_3430-1.jpg?ex=6999c015&is=69986e95&hm=f13a2cee3f06cdd9c4b01e7dd851cc85c21d927a122f73790d42efbeb6bab863&=&format=webp&width=699&height=931",
            # "hoài linh":"https://cdn.discordapp.com/attachments/1439553447384060047/1474833395585519777/hoai_linh.mp4?ex=699b4922&is=6999f7a2&hm=351ce21d6fc3090ce0c77e448a4575547478af531e58300d259b91bb8f5d8d61&",
            # "active windows":"irm https://get.activated.win | iex",
            # "na":"https://cdn.discordapp.com/attachments/1439553447384060047/1475075585691877488/image.png?ex=699c2ab1&is=699ad931&hm=0198c5621ae3e9c6bb96054a7ef6f8964fcbc748ebb11e551f0b4adc783799ee&",
            # "dương quỳnh như":"https://cdn.discordapp.com/attachments/1439553447384060047/1475076842900815875/image.png?ex=699c2bdc&is=699ada5c&hm=5414d38f4483dddefa6e149162c0eef6ddc9600aaac1719c84a463890f794376&",
            # "anh tôi đấy":"đấy a độ t đấy, cmay cứ trêu đi, gia đình hạnh phúc, vợ con ấm no, con người hào phóng, nói thẳng ra là chả thiếu chi https://cdn.discordapp.com/attachments/1439553447384060047/1475499963961311344/609980560567487752.mp4?ex=699db5ec&is=699c646c&hm=0fc84bc12fa6a73e2d7456f0cf5b90c986f2f99ce1d0b81408888cf2a91cd64e&",
            "tài liệu ở đây":"https://discord.com/channels/1184348724999225355/1184348725632581713",
            "tài liệu ở đâu":"https://discord.com/channels/1184348724999225355/1184348725632581713",
            "tài liệu ở đâu rồi":"https://discord.com/channels/1184348724999225355/1184348725632581713",
            "hướng dẫn sài tài liệu":"https://discord.com/channels/1184348724999225355/1184348725632581713",
            "tài liệu ở": "https://discord.com/channels/1184348724999225355/1184348725632581713",
            "thấy gớm":"https://media.discordapp.net/attachments/1439553447384060047/1478848047373877399/636287343_1254109646812869_984951542176234088_n.png?ex=69a9e412&is=69a89292&hm=ab0ceecb6bdd25de05a1d98eea7a592ab34e4af543d8d6fdd46745ba08548db7&=&format=webp&quality=lossless&width=705&height=940",  
            "nói lại":"https://media.discordapp.net/attachments/1439553447384060047/1478848140479168763/639127889_1254109610146206_4832400766879983140_n.png?ex=69a9e428&is=69a892a8&hm=aec2453fe5e2fba91a5a4d155c4f8808a45f1fbeceb0d800dc6a4295bfc39dc9&=&format=webp&quality=lossless&width=705&height=940",
            "test ielts":"https://youpass.vn/luyen-thi/ielts/reading?quiz_type=quiz&status=unfinished",
            "test toeic":"https://study4.com/tests/toeic/",
            "test lgbt":"https://www.wikihow.com/Relationships/Lgbtq-Quiz",
            "lhp vs ptnk":"https://cdn.discordapp.com/attachments/1446866616452386856/1480959155090231498/1.mp4?ex=69b19231&is=69b040b1&hm=6b026ea88132491b280f100a4b40612da204a8cf81874c34714259a64d5a1204&",
            "ptnk vs lhp":"https://cdn.discordapp.com/attachments/1446866616452386856/1480959155090231498/1.mp4?ex=69b19231&is=69b040b1&hm=6b026ea88132491b280f100a4b40612da204a8cf81874c34714259a64d5a1204&",
            "đề thi ở":"sử dụng lệnh /sukien sau đó gửi, nếu ko có thì tìm trong kênh https://discord.com/channels/1184348724999225355/1447538537753743460",
            "đề thi ở đâu":"sử dụng lệnh /sukien sau đó gửi, nếu ko có thì tìm trong kênh https://discord.com/channels/1184348724999225355/1447538537753743460",
            "hướng dẫn sài":"https://discord.com/channels/1184348724999225355/1184348725632581713/1394786706552524931",
            "hướng dẫn kênh":"https://discord.com/channels/1184348724999225355/1184348725632581713/1394786706552524931",
            "điểm chuẩn hub":"https://media.discordapp.net/attachments/1486759905431130175/1497267310598033459/cc3b4ng20be1bb9120hubfinal201-1755898941713-1755898942603944920565.png?ex=69ece658&is=69eb94d8&hm=17235617a54de671768f1eef6df571ea5e959c58f3955c9076418973498acf47&=&format=webp&quality=lossless&width=934&height=934",
            # "trình":"https://www.youtube.com/watch?v=7kO_ALcwNAw",



        }
        
        # Dictionary chứa các từ bị timeout 10 ngày (khác với banned_phrases)11
        # Thêm các từ cần timeout vào đây
        self.timeout_phrases = [
            
            # Thêm các từ timeout khác vào đây
        ]










    def _is_timed_out(self, member: discord.Member) -> bool:
        return member.is_timed_out()

    def _load_suggestions(self):
        """Load suggestions from JSON file"""
        try:
            if os.path.exists(self.suggestions_file):
                with open(self.suggestions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {"suggestions": []}
        except Exception as e:
            logger.error(f"Error loading suggestions: {e}")
            return {"suggestions": []}
    
    def _save_suggestions(self, data):
        """Save suggestions to JSON file"""
        try:
            with open(self.suggestions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logger.error(f"Error saving suggestions: {e}")
            return False

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Xử lý lỗi commands - bỏ qua CommandNotFound để không ảnh hưởng đến on_message events"""
        if isinstance(error, commands.CommandNotFound):
            # Bỏ qua lỗi CommandNotFound vì chúng ta đang xử lý các lệnh trong on_message
            return
        else:
            # Log các lỗi khác
            logger.error(f"Command error in {ctx.command}: {error}")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Tự động xóa timeout cho Mod nếu họ bị timeout dưới 2 giờ"""
        # Kiểm tra xem có thay đổi về timeout không
        if before.timed_out_until == after.timed_out_until:
            return
        
        # Nếu member vừa bị timeout (before không bị timeout, after bị timeout)
        if not before.is_timed_out() and after.is_timed_out():
            # Danh sách ID role Mod được tự động xóa timeout 
            MOD_ROLE_IDS = [
                1472560579007746079,1401564796553265162,1241969973086388244,1484957377135509667
                      # Supervisor role khác
            ]
            
            # Kiểm tra xem member có role Mod không
            has_mod_role = any(role.id in MOD_ROLE_IDS for role in after.roles)
            
            if has_mod_role:
                # Kiểm tra thời gian timeout còn lại
                if after.timed_out_until:
                    time_remaining = after.timed_out_until - datetime.now(after.timed_out_until.tzinfo)
                    
                    # Chỉ xóa timeout nếu thời gian còn lại dưới 2 tiếng (7200 giây)
                    if time_remaining.total_seconds() < 7200:
                        try:
                            # Xóa timeout ngay lập tức
                            await after.timeout(None, reason="Auto-remove timeout for Mod (under 2 hours)")
                            logger.info(f"[AUTO-REMOVE] Removed timeout for Mod: {after.name} (time remaining: {time_remaining.total_seconds():.0f}s)")
                            
                        except discord.Forbidden:
                            logger.error(f"[ERROR] Bot missing permission to remove timeout for Mod: {after.name}")
                        except Exception as e:
                            logger.error(f"[ERROR] Failed to auto-remove timeout for Mod {after.name}: {e}")
                    else:
                        logger.info(f"[SKIP] Mod {after.name} has timeout over 2 hours ({time_remaining.total_seconds():.0f}s), not removing")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Bỏ qua tin nhắn của bot NGAY LẬP TỨC
        if message.author.bot:
            return
        
        if message.author == self.bot.user:
            return

        # ===== DEBUG LOG (TẠM THỜI) =====
        if message.guild:
            logger.info(f"[DEBUG] Message from {message.author.name} in {message.guild.name} (ID: {message.guild.id})")
            logger.info(f"[DEBUG] Channel ID: {message.channel.id}")
            logger.info(f"[DEBUG] BOT_FILTER_CHANNELS = {config.BOT_FILTER_CHANNELS if hasattr(config, 'BOT_FILTER_CHANNELS') else 'Not defined'}")
            logger.info(f"[DEBUG] Is in filter channel? {message.channel.id in config.BOT_FILTER_CHANNELS if hasattr(config, 'BOT_FILTER_CHANNELS') and config.BOT_FILTER_CHANNELS else False}")

        # ===== KIỂM TRA KÊNH LỌC BOT (ƯU TIÊN TRƯỚC) =====
        # Nếu tin nhắn được gửi trong kênh lọc bot
        if message.guild and hasattr(config, 'BOT_FILTER_CHANNELS') and config.BOT_FILTER_CHANNELS and message.channel.id in config.BOT_FILTER_CHANNELS:
            logger.info(f"[BOT FILTER] Detected message in bot filter server from {message.author.name}")
            try:
                # Xóa tin nhắn ngay lập tức
                await message.delete()
                logger.info(f"[BOT FILTER] ✅ Deleted message from {message.author.name} in bot filter server")
                
                # Timeout 10 ngày
                await message.author.timeout(
                    timedelta(days=10),
                    reason="Tự động timeout trong server lọc bot"
                )
                logger.info(f"[BOT FILTER] ✅ Timed out {message.author.name} for 10 days")
                
                # Gửi thông báo (tùy chọn)
                await message.channel.send(
                    f"🚫 {message.author.mention} đã bị cấm nhắn tin 10 ngày do gửi tin nhắn trong channel lọc bot! CẢNH BÁO⚠️ :  KÊNH NÀY NHẰM MỤC ĐÍCH ĐỂ TỰ ĐỘNG BAN BOT VÀ/HOẶC CÁC TÀI KHOẢN TỰ ĐỘNG. NẾU BẠN NHẮN VÀO KÊNH NÀY SẼ BỊ HỆ THỐNG TỰ ĐỘNG BAN NGAY LẬP TỨC.Vui lòng rời khỏi đây nếu không biết bạn đang làm gì. https://cdn.discordapp.com/attachments/1472557179985727710/1478444884934529337/image.png?ex=69a86c98&is=69a71b18&hm=58d7c9be842ec370334e3d108e9702ff9ff3c6ac3e5eed573c87975e5f86b6d9&"
                )
                    
            except discord.Forbidden:
                logger.error(f"[BOT FILTER] ❌ Bot missing permission to delete message or timeout user!")
            except discord.NotFound:
                logger.warning(f"[BOT FILTER] ⚠️ Message or user not found")
            except Exception as e:
                logger.error(f"[BOT FILTER] ❌ Error: {e}")
            
            # Dừng xử lý các sự kiện khác
            return

        # LOG: Kiểm tra mọi tin nhắn (đã tắt)
        # logger.info(f"[MESSAGE] From: {message.author.name} | Content: {message.content[:50]}")
        # logger.info(f"[CHECK] mention_everyone: {message.mention_everyone}")
        # logger.info(f"[CHECK] Has @everyone/@here in content: {'@everyone' in message.content or '@here' in message.content}")

        # ===== CHUẨN HÓA NỘI DUNG TIN NHẮN (ĐẶT Ở ĐẦU) =====
        message_content = message.content.lower().strip()

        # ===== HỆ THỐNG XÓA TỪ CẤM (HOẠT ĐỘNG Ở TẤT CẢ CÁC KÊNH - ƯU TIÊN CAO) =====
        # Kiểm tra tin nhắn chứa từ cấm -> xóa ngay tin nhắn người dùng (KHÔNG timeout)
        banned_phrases = ["chó độ", "độ ngu", "từ cha", "độ shisha", "xin lỗi", "minh thư"]
        if any(phrase in message_content for phrase in banned_phrases):
            if message.guild:
                permissions = message.channel.permissions_for(message.guild.me)
                if not permissions.manage_messages:
                    logger.warning("Missing Manage Messages permission to delete user message.")
                    return
            try:
                await message.delete()
                logger.info(f"[BANNED PHRASE] Deleted message from {message.author.name} containing banned phrase")
            except Exception as e:
                logger.warning(f"Failed to delete message: {e}")
            return

        # ===== HỆ THỐNG TIMEOUT TỪ BỊ CẤM (HOẠT ĐỘNG Ở TẤT CẢ CÁC KÊNH) =====
        # Kiểm tra từ trong timeout_phrases -> timeout 10 ngày và xóa tin nhắn
        if any(phrase in message_content for phrase in self.timeout_phrases):
            try:
                # Xóa tin nhắn vi phạm
                await message.delete()
                
                # Timeout người dùng 25 ngày
                if message.guild and isinstance(message.author, discord.Member):
                    try:
                        await message.author.timeout(
                            timedelta(days=15),
                            reason="15 days time out"
                        )
                        logger.info(f"[TIMEOUT] User {message.author.name} timed out for 15 days because of banned phrase ")
                        
                        # Gửi thông báo
                        await message.channel.send(
                            f"⚠️ Banned phrase {message.author.mention} https://media.discordapp.net/attachments/1439553447384060047/1481389173846970629/image.png?ex=69b322ad&is=69b1d12d&hm=6063cacfdc6c86f4acf7421b1df4455bec2f3aa8c6d2652c62a079b6ee42a25a&=&format=webp&quality=lossless&width=851&height=729"
                        )
                    except discord.Forbidden:
                        logger.error(f"[ERROR] Bot missing 'Moderate Members' permission!")
                    except Exception as e:
                        logger.error(f"[ERROR] Failed to timeout user: {e}")
            except Exception as e:
                logger.warning(f"Failed to delete message: {e}")
            return

        # Kiểm tra nếu tin nhắn chứa @everyone hoặc @here (áp dụng cho TẤT CẢ các kênh)
        # Kiểm tra cả mention thực và text @everyone/@here
        has_everyone_text = '@everyone' in message.content or '@here' in message.content
        if message.mention_everyone or has_everyone_text:
            # logger.info(f"[DETECTED] @everyone/@here mentioned by {message.author.name}")
            
            # Kiểm tra xem người dùng có phải là admin không
            if message.guild and isinstance(message.author, discord.Member):
                # logger.info(f"[CHECK] Is in guild: {message.guild.name}")
                # logger.info(f"[CHECK] Author is admin: {message.author.guild_permissions.administrator}")
                
                if not message.author.guild_permissions.administrator:
                    # logger.info(f"[ACTION] Attempting to timeout {message.author.name}")
                    try:
                        # Xóa tin nhắn trước
                        try:
                            await message.delete()
                            # logger.info(f"[SUCCESS] Message deleted")
                        except discord.NotFound:
                            logger.warning("Message already deleted")
                        except Exception as e:
                            logger.error(f"Error deleting message: {e}")
                        
                        # Timeout 27 ngày
                        await message.author.timeout(
                            timedelta(days=27),
                            reason="Tag @everyone/@here không được phép"
                        )
                        # logger.info(f"[SUCCESS] User {message.author.name} timed out for 27 days")
                        
                        # Gửi thông báo
                        await message.channel.send(
                            f"⚠️ {message.author.mention} đã bị timeout 365 ngày vì tag everyone/here! https://cdn.discordapp.com/attachments/1472557179985727710/1478444884934529337/image.png?ex=69a86c98&is=69a71b18&hm=58d7c9be842ec370334e3d108e9702ff9ff3c6ac3e5eed573c87975e5f86b6d9&"
                        )
                        
                        return
                    except discord.Forbidden:
                        # Bot thiếu quyền - gửi thông báo cho admin
                        logger.error(f"[ERROR] Bot missing 'Moderate Members' permission!")
                        error_msg = await message.channel.send(
                            f"❌ Bot không có quyền timeout người dùng! Vui lòng cấp quyền **Moderate Members** cho bot."
                        )
                        await asyncio.sleep(15)
                        try:
                            await error_msg.delete()
                        except:
                            pass
                    except discord.NotFound as e:
                        logger.warning(f"Message or user not found: {e}")
                    except Exception as e:
                        logger.error(f"[ERROR] Unexpected error: {e}")
                else:
                    pass
                    # logger.info(f"[SKIP] User {message.author.name} is admin, no action taken")
            else:
                pass
                # logger.warning(f"[SKIP] Not in guild or not a member")

        # Kiểm tra xem channel có được phép không trước khi xử lý trigger
        if not is_allowed_channel_for_message(message.channel.id):
            return

        # ===== HỆ THỐNG TRIGGER RESPONSES (CHỈ Ở CÁC KÊNH ĐƯỢC PHÉP) =====
        # Kiểm tra các cụm từ trigger và reply tự động
        # Sử dụng word boundary để chỉ khớp từ đơn lẻ, không khớp từ nằm trong từ khác
        
        # Kiểm tra pattern "X à X" (tên lặp lại 2 lần) - ƯU TIÊN TRƯỚC
        # Pattern: bất kỳ từ nào, theo sau bởi " à ", rồi lặp lại từ đó
        name_pattern = r'\b(\w+)\s+à111111\s+\1\b'
        match = re.search(name_pattern, message_content)
        
        if match:
            # Tìm thấy pattern "X à X"
            try:
                await message.reply("https://cdn.discordapp.com/attachments/1439553447384060047/1472551479264018537/tiktok_video_1.mp4?ex=6992fbef&is=6991aa6f&hm=57ebecef25de55920e8ef02f34d6a112d2c3ba729d7b60b13e127f965d64c247&")
                logger.info(f"[NAME PATTERN] Triggered by '{match.group(0)}' from {message.author.name}")
            except Exception as e:
                logger.error(f"Error in name pattern trigger: {e}")
            return
        
        # Kiểm tra các trigger thông thường (sau khi kiểm tra pattern)
        for trigger, response in self.trigger_responses.items():
            # Sử dụng regex với word boundary để khớp chính xác
            if re.search(r'\b' + re.escape(trigger) + r'\b', message_content):
                try:
                    await message.reply(response)
                except Exception as e:
                    logger.error(f"Error in trigger response for '{trigger}': {e}")
                return  # Dừng xử lý sau khi reply

        # Kiểm tra xem channel có được phép không (các tính năng khác chỉ áp dụng cho kênh được phép)
        if not is_allowed_channel_for_message(message.channel.id):
            return

        if message.guild and isinstance(message.author, discord.Member):
            if self._is_timed_out(message.author):
                try:
                    await message.delete()
                except Exception:
                    pass
                return

        # Greeting feature - các từ phải đơn lẻ
        greetings = []
        
        # Kiểm tra xem có từ nào trong greetings là từ riêng lẻ
        # Sử dụng regex để kiểm tra word boundaries
        for greeting in greetings:
            if re.search(r'\b' + re.escape(greeting) + r'\b', message_content):
                # Mention người dùng
                bot_message = await message.reply(f'Ờ anh chào {message.author.mention} Nhá 👋 em là {message.author.mention} hả, em chối làm sao được ')
                
                # Xóa tin nhắn sau 10 giây
                await asyncio.sleep(10)
                try:
                    await bot_message.delete()
                    await message.delete()
                except:
                    pass
                return  # Dừng xử lý sau khi reply
        
        # Kiểm tra tin nhắn chứa "khô gà1"
        if 'khô gà1' in message_content:
            bot_message = await message.reply('https://media.discordapp.net/attachments/1439553447384060047/1461010970682986658/508669079_1261013605577267_5195994080152027537_n.png?ex=6968ffff&is=6967ae7f&hm=75e359f1213ffba9f8fb756922147bb6cf8daa5af70d8db44fa1967a887ce733&=&format=webp&quality=lossless&width=1191&height=894')
            
            # Xóa tin nhắn sau 10 giây
            await asyncio.sleep(10)
            try:
                await bot_message.delete()
                await message.delete()
            except:
                pass
            return  # Thêm return
        
        # Kiểm tra tin nhắn chứa "xây trường", "xây nhà" hoặc "việc tốt anh độ"
        good_deeds = []
        for deed in good_deeds:
            if deed in message_content:
                bot_message = await message.reply(f'Anh gửi Khô Gà mixi cho {message.author.mention} nhé 🥳 https://media.discordapp.net/attachments/1459229057706364939/1461582560332087399/shopee_vn-11134103-22120-depw1vmsf0kv16.png?ex=696b1455&is=6969c2d5&hm=eddc74afe016d7f9dd4e1922f6ab7930a0446e1e29ba21bc988cf1c817a93d58&=&format=webp&quality=lossless&width=555&height=740')
                
                # Xóa tin nhắn sau 20 giây
                await asyncio.sleep(10)
                try:
                    await bot_message.delete()
                    await message.delete()
                except:
                    pass
                return  # Thêm return
        
        # Kiểm tra lệnh !id để hiển thị ID người dùng
        if message_content.startswith('!id'):
            try:
                # Kiểm tra xem có mention ai không
                if message.mentions:
                    target_user = message.mentions[0]
                else:
                    target_user = message.author
                
                # Tạo embed hiển thị ID
                embed = discord.Embed(
                    title=f"🆔 Thông tin ID của {target_user.display_name}",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="User ID", value=f"`{target_user.id}`", inline=False)
                embed.add_field(name="Username", value=f"`{target_user.name}`", inline=True)
                embed.add_field(name="Display Name", value=f"`{target_user.display_name}`", inline=True)
                embed.set_thumbnail(url=target_user.display_avatar.url)
                embed.set_footer(text=f"Yêu cầu bởi {message.author.display_name}")
                
                bot_message = await message.reply(embed=embed)
                
                # Xóa tin nhắn sau 10 giây
                await asyncio.sleep(10)
                try:
                    await bot_message.delete()
                    await message.delete()
                except:
                    pass
            except Exception as e:
                logger.error(f"Error showing user ID: {e}")
            return  # Thêm return để tránh xử lý tiếp
        
        # Kiểm tra lệnh !avt để hiển thị avatar
        if message_content.startswith('!485357927355avt'):
            logger.info(f"Processing !avt command from {message.author.name} (ID: {message.author.id})")
            try:
                # Kiểm tra xem có mention ai không
                if message.mentions:
                    target_user = message.mentions[0]
                else:
                    target_user = message.author
                
                logger.info(f"Target user: {target_user.name}")
                
                # Lấy avatar URL
                avatar_url = target_user.display_avatar.url
                
                # Tạo embed hiển thị avatar
                embed = discord.Embed(
                    title=f"🖼️ Avatar của {target_user.display_name}",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                embed.set_image(url=avatar_url)
                embed.set_footer(text=f"Yêu cầu bởi {message.author.display_name}")
                
                # Thêm link tải avatar
                embed.add_field(
                    name="📥 Tải avatar",
                    value=f"[Click để tải]({avatar_url})",
                    inline=False
                )
                
                bot_message = await message.reply(embed=embed)
                
                # Xóa tin nhắn sau 30 giây
                await asyncio.sleep(30)
                try:
                    await bot_message.delete()
                    await message.delete()
                except:
                    pass
            except Exception as e:
                logger.error(f"Error showing avatar: {e}")
            return  # Thêm return để tránh xử lý tiếp
        
        # Kiểm tra lệnh !info để hiển thị thông tin server
        if message_content.startswith('!info'):
            try:
                if not message.guild:
                    bot_message = await message.reply("❌ Lệnh này chỉ hoạt động trong server!")
                    await asyncio.sleep(5)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                    return
                
                guild = message.guild
                
                # Đếm số lượng thành viên theo loại
                total_members = guild.member_count
                humans = len([m for m in guild.members if not m.bot])
                bots = len([m for m in guild.members if m.bot])
                online = len([m for m in guild.members if m.status != discord.Status.offline])
                
                # Tạo embed hiển thị thông tin
                embed = discord.Embed(
                    title=f"📊 Thông tin Server: {guild.name}",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                
                # Thêm icon server nếu có
                if guild.icon:
                    embed.set_thumbnail(url=guild.icon.url)
                
                # Thông tin cơ bản
                embed.add_field(name="👥 Tổng thành viên", value=f"`{total_members}`", inline=True)
                embed.add_field(name="👤 Người dùng", value=f"`{humans}`", inline=True)
                embed.add_field(name="🤖 Bot", value=f"`{bots}`", inline=True)
                embed.add_field(name="🟢 Online", value=f"`{online}`", inline=True)
                embed.add_field(name="📅 Ngày tạo", value=f"<t:{int(guild.created_at.timestamp())}:D>", inline=True)
                embed.add_field(name="👑 Chủ sở hữu", value=f"`{guild.owner.name}`" if guild.owner else "`N/A`", inline=True)
                
                # Thống kê kênh
                text_channels = len(guild.text_channels)
                voice_channels = len(guild.voice_channels)
                categories = len(guild.categories)
                
                embed.add_field(name="💬 Kênh văn bản", value=f"`{text_channels}`", inline=True)
                embed.add_field(name="🔊 Kênh voice", value=f"`{voice_channels}`", inline=True)
                embed.add_field(name="📁 Danh mục", value=f"`{categories}`", inline=True)
                
                # Thống kê role
                embed.add_field(name="🎭 Số lượng role", value=f"`{len(guild.roles)}`", inline=True)
                embed.add_field(name="😀 Emoji", value=f"`{len(guild.emojis)}`", inline=True)
                embed.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
                
                embed.set_footer(text=f"Yêu cầu bởi {message.author.display_name}")
                
                bot_message = await message.reply(embed=embed)
                
                # Xóa tin nhắn sau 30 giây111
                await asyncio.sleep(5)
                try:
                    await bot_message.delete()
                    await message.delete()
                except:
                    pass
                
            except Exception as e:
                logger.error(f"Error showing server info: {e}")
            return
        
        # Kiểm tra lệnh !timeout để xóa timeout của tất cả người dùng
        if message_content.startswith('!1timeout'):
            # Danh sách ID role được phép sử dụng
            ALLOWED_ROLE_IDS = [
               1401564796553265162,1472560579007746079,1241969973086388244   # Supervisor
            ]
            
            # Kiểm tra quyền admin hoặc role được phép
            is_admin = message.author.guild_permissions.administrator
            has_allowed_role = any(role.id in ALLOWED_ROLE_IDS for role in message.author.roles)
            
            # Debug: log thông tin để kiểm tra
            logger.info(f"User {message.author.name} (ID: {message.author.id}) attempted !1timeout")
            logger.info(f"Is admin: {is_admin}")
            logger.info(f"User roles: {[f'{role.name} (ID: {role.id})' for role in message.author.roles]}")
            logger.info(f"Has allowed role: {has_allowed_role}")
            
            if not (is_admin or has_allowed_role):
                bot_message = await message.reply(f"❌ Bạn không có quyền sử dụng lệnh này!\n**Your roles:** {', '.join([f'{role.name} ({role.id})' for role in message.author.roles if role.name != '@everyone'])}")
                await asyncio.sleep(10)
                try:
                    await bot_message.delete()
                    await message.delete()
                except:
                    pass
                return
            
            try:
                # Đếm số người bị timeout dưới 2 tiếng
                timed_out_members = []
                skipped_members = []
                
                for member in message.guild.members:
                    if member.is_timed_out():
                        # Kiểm tra thời gian timeout còn lại
                        if member.timed_out_until:
                            time_remaining = member.timed_out_until - datetime.now(member.timed_out_until.tzinfo)
                            
                            # Nếu thời gian còn lại dưới 2 tiếng (7200 giây)
                            if time_remaining.total_seconds() < 7200:
                                timed_out_members.append(member)
                            else:
                                skipped_members.append(member)
                
                if not timed_out_members:
                    if skipped_members:
                        bot_message = await message.reply(f"⚠️ Không có người dùng nào bị timeout dưới 2 tiếng!\n({len(skipped_members)} người bị timeout trên 2 tiếng sẽ không được xóa)")
                    else:
                        bot_message = await message.reply("✅ Không có người dùng nào bị timeout!")
                    await asyncio.sleep(5)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                    return
                
                # Xóa timeout cho các thành viên có timeout dưới 2 tiếng
                success_count = 0
                fail_count = 0
                
                status_msg = f"⏳ Đang xóa timeout cho {len(timed_out_members)} người dùng (dưới 2 tiếng)..."
                if skipped_members:
                    status_msg += f"\n⚠️ Bỏ qua {len(skipped_members)} người (timeout trên 2 tiếng)"
                
                status_message = await message.reply(status_msg)
                
                for member in timed_out_members:
                    try:
                        await member.timeout(None, reason=f"Timeout removed by {message.author.name}")
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to remove timeout for {member.name}: {e}")
                        fail_count += 1
                
                # Tạo embed kết quả
                embed = discord.Embed(
                    title="✅ XÓA TIMEOUT HOÀN TẤT",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Thành công", value=f"✅ {success_count} người", inline=True)
                embed.add_field(name="Thất bại", value=f"❌ {fail_count} người", inline=True)
                embed.set_footer(text=f"Thực hiện bởi {message.author.display_name}")
                
                await status_message.edit(content=None, embed=embed)
                
                # Xóa tin nhắn sau 15 giây
                await asyncio.sleep(15)
                try:
                    await status_message.delete()
                    await message.delete()
                except:
                    pass
                
            except Exception as e:
                logger.error(f"Error in timeout removal: {e}")
                error_msg = await message.reply("❌ Có lỗi xảy ra khi xóa timeout!")
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                    await message.delete()
                except:
                    pass
        
        # ===== HỆ THỐNG ĐỀ XUẤT CHỨC NĂNG =====
        # Lệnh !add <tiêu đề> | <mô tả> - Gửi đề xuất chức năng mới
        if message_content.startswith('!add '):
            try:
                # Lấy nội dung sau !add
                content = message.content[5:].strip()
                
                if not content:
                    bot_message = await message.reply("❌ Vui lòng nhập nội dung đề xuất!\n**Cú pháp:** `!add <tiêu đề> | <mô tả>`\n**Ví dụ:** `!add Lệnh chơi nhạc | Thêm lệnh !play để phát nhạc trong voice channel`")
                    await asyncio.sleep(10)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                    return
                
                # Tách tiêu đề và mô tả
                if '|' in content:
                    parts = content.split('|', 1)
                    title = parts[0].strip()
                    description = parts[1].strip()
                else:
                    title = content
                    description = "Không có mô tả chi tiết"
                
                # Load dữ liệu hiện tại
                data = self._load_suggestions()
                
                # Tạo ID mới
                new_id = len(data['suggestions']) + 1
                
                # Tạo đề xuất mới
                suggestion = {
                    "id": new_id,
                    "title": title,
                    "description": description,
                    "author_id": message.author.id,
                    "author_name": message.author.name,
                    "timestamp": datetime.now().isoformat(),
                    "status": "pending"
                }
                
                # Thêm vào danh sách
                data['suggestions'].append(suggestion)
                
                # Lưu vào file
                if self._save_suggestions(data):
                    embed = discord.Embed(
                        title="✅ ĐỀ XUẤT ĐÃ ĐƯỢC GỬI",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="📝 Tiêu đề", value=title, inline=False)
                    embed.add_field(name="📄 Mô tả", value=description, inline=False)
                    embed.add_field(name="🆔 ID Đề xuất", value=f"`#{new_id}`", inline=True)
                    embed.set_footer(text=f"Đề xuất bởi {message.author.display_name}")
                    
                    bot_message = await message.reply(embed=embed)
                    
                    # Gửi thông báo cho admin (nếu có channel riêng)
                    # TODO: Bạn có thể thêm logic gửi thông báo đến channel admin ở đây
                    
                    await asyncio.sleep(15)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                else:
                    bot_message = await message.reply("❌ Có lỗi khi lưu đề xuất. Vui lòng thử lại!")
                    await asyncio.sleep(5)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                
            except Exception as e:
                logger.error(f"Error in !add command: {e}")
                error_msg = await message.reply("❌ Có lỗi xảy ra khi xử lý đề xuất!")
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                    await message.delete()
                except:
                    pass
            return
        

            
















        # Lệnh !viewadd - Xem danh sách đề xuất
        if message_content.startswith('!viewadd'):
            try:
                data = self._load_suggestions()
                suggestions = data.get('suggestions', [])
                
                if not suggestions:
                    bot_message = await message.reply("📭 Chưa có đề xuất nào!")
                    await asyncio.sleep(5)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                    return
                
                # Lọc theo status nếu có tham số
                status_filter = None
                if len(message_content.split()) > 1:
                    status_param = message_content.split()[1].lower()
                    if status_param in ['pending', 'approved', 'rejected']:
                        status_filter = status_param
                        suggestions = [s for s in suggestions if s.get('status') == status_filter]
                
                if not suggestions:
                    bot_message = await message.reply(f"📭 Không có đề xuất nào với trạng thái `{status_filter}`!")
                    await asyncio.sleep(5)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                    return
                
                # Tạo embed hiển thị
                embed = discord.Embed(
                    title="📋 DANH SÁCH ĐỀ XUẤT CHỨC NĂNG",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                
                # Hiển thị tối đa 10 đề xuất gần nhất
                recent_suggestions = suggestions[-10:]
                
                for suggestion in reversed(recent_suggestions):
                    status_emoji = {
                        'pending': '⏳',
                        'approved': '✅',
                        'rejected': '❌'
                    }.get(suggestion.get('status', 'pending'), '❓')
                    
                    field_value = f"**Mô tả:** {suggestion.get('description', 'N/A')}\n"
                    field_value += f"**Người đề xuất:** {suggestion.get('author_name', 'Unknown')}\n"
                    field_value += f"**Trạng thái:** {status_emoji} {suggestion.get('status', 'pending').upper()}"
                    
                    embed.add_field(
                        name=f"#{suggestion['id']} - {suggestion.get('title', 'No title')}",
                        value=field_value,
                        inline=False
                    )
                
                total = len(suggestions)
                embed.set_footer(text=f"Tổng số đề xuất: {total} | Hiển thị: {len(recent_suggestions)} gần nhất")
                
                bot_message = await message.reply(embed=embed)
                
                await asyncio.sleep(30)
                try:
                    await bot_message.delete()
                    await message.delete()
                except:
                    pass
                
            except Exception as e:
                logger.error(f"Error in !viewadd command: {e}")
                error_msg = await message.reply("❌ Có lỗi khi hiển thị danh sách đề xuất!")
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                    await message.delete()
                except:
                    pass
            return
        
        # Lệnh !approveadd <id> hoặc !rejectadd <id> - Admin duyệt/từ chối đề xuất
        if message_content.startswith('!approveadd ') or message_content.startswith('!rejectadd '):
            # Danh sách ID role được phép
            ALLOWED_ROLE_IDS = [
                1185158470958333953,  # Mod
                1401564796553265162,
                1185183734153097296   # Supervisor
            ]
            
            # Kiểm tra quyền
            is_admin = message.author.guild_permissions.administrator
            has_allowed_role = any(role.id in ALLOWED_ROLE_IDS for role in message.author.roles)
            
            if not (is_admin or has_allowed_role):
                bot_message = await message.reply("❌ Bạn không có quyền sử dụng lệnh này!")
                await asyncio.sleep(5)
                try:
                    await bot_message.delete()
                    await message.delete()
                except:
                    pass
                return
            
            try:
                # Xác định action (approve hoặc reject)
                is_approve = message_content.startswith('!approveadd')
                command = '!approveadd' if is_approve else '!rejectadd'
                
                # Lấy ID đề xuất
                parts = message_content.split()
                if len(parts) < 2:
                    bot_message = await message.reply(f"❌ Vui lòng nhập ID đề xuất!\n**Cú pháp:** `{command} <id>`")
                    await asyncio.sleep(5)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                    return
                
                try:
                    suggestion_id = int(parts[1])
                except ValueError:
                    bot_message = await message.reply("❌ ID đề xuất không hợp lệ!")
                    await asyncio.sleep(5)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                    return
                
                # Load dữ liệu
                data = self._load_suggestions()
                suggestions = data.get('suggestions', [])
                
                # Tìm đề xuất
                suggestion = None
                for s in suggestions:
                    if s['id'] == suggestion_id:
                        suggestion = s
                        break
                
                if not suggestion:
                    bot_message = await message.reply(f"❌ Không tìm thấy đề xuất với ID `#{suggestion_id}`!")
                    await asyncio.sleep(5)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                    return
                
                # Cập nhật trạng thái
                new_status = 'approved' if is_approve else 'rejected'
                suggestion['status'] = new_status
                suggestion['reviewed_by'] = message.author.name
                suggestion['reviewed_at'] = datetime.now().isoformat()
                
                # Lưu lại
                if self._save_suggestions(data):
                    status_emoji = '✅' if is_approve else '❌'
                    status_text = 'PHÊ DUYỆT' if is_approve else 'TỪ CHỐI'
                    status_color = discord.Color.green() if is_approve else discord.Color.red()
                    
                    embed = discord.Embed(
                        title=f"{status_emoji} ĐÃ {status_text} ĐỀ XUẤT",
                        color=status_color,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="🆔 ID", value=f"`#{suggestion['id']}`", inline=True)
                    embed.add_field(name="📝 Tiêu đề", value=suggestion['title'], inline=False)
                    embed.add_field(name="👤 Người đề xuất", value=suggestion['author_name'], inline=True)
                    embed.add_field(name="👮 Xử lý bởi", value=message.author.display_name, inline=True)
                    embed.set_footer(text=f"Trạng thái: {new_status.upper()}")
                    
                    bot_message = await message.reply(embed=embed)
                    
                    await asyncio.sleep(15)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                else:
                    bot_message = await message.reply("❌ Có lỗi khi cập nhật trạng thái!")
                    await asyncio.sleep(5)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                
            except Exception as e:
                logger.error(f"Error in approve/reject command: {e}")
                error_msg = await message.reply("❌ Có lỗi xảy ra!")
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                    await message.delete()
                except:
                    pass
            return
        
        # Kiểm tra lệnh !roles để hiển thị danh sách roles và ID
        if message_content.startswith('!roles'):
            try:
                if not message.guild:
                    bot_message = await message.reply("❌ Lệnh này chỉ hoạt động trong server!")
                    await asyncio.sleep(5)
                    try:
                        await bot_message.delete()
                        await message.delete()
                    except:
                        pass
                    return
                
                # Lấy danh sách roles
                roles = message.guild.roles
                
                # Tạo embed hiển thị
                embed = discord.Embed(
                    title=f"📋 Danh sách Roles trong {message.guild.name}",
                    color=discord.Color.gold(),
                    timestamp=datetime.now()
                )
                
                # Sắp xếp roles theo position (cao nhất trước)
                sorted_roles = sorted(roles, key=lambda r: r.position, reverse=True)
                
                role_list = ""
                for role in sorted_roles:
                    if role.name != "@everyone":  # Bỏ qua @everyone
                        role_list += f"**{role.name}**\nID: `{role.id}`\nColor: {role.color}\n\n"
                
                if not role_list:
                    role_list = "Không có role nào (ngoài @everyone)"
                
                # Chia nhỏ nếu quá dài (Discord embed field limit is 1024 characters)
                if len(role_list) > 1024:
                    # Chia thành nhiều field
                    chunks = [role_list[i:i+1024] for i in range(0, len(role_list), 1024)]
                    for i, chunk in enumerate(chunks):
                        embed.add_field(
                            name=f"Roles (Phần {i+1})" if len(chunks) > 1 else "Roles",
                            value=chunk,
                            inline=False
                        )
                else:
                    embed.add_field(name="Roles", value=role_list, inline=False)
                
                embed.set_footer(text=f"Tổng số roles: {len([r for r in roles if r.name != '@everyone'])} | Yêu cầu bởi {message.author.display_name}")
                
                bot_message = await message.reply(embed=embed)
                
                # Xóa tin nhắn sau 30 giây
                await asyncio.sleep(30)
                try:
                    await bot_message.delete()
                    await message.delete()
                except:
                    pass
            except Exception as e:
                logger.error(f"Error showing roles: {e}")
            return


async def setup(bot):
    await bot.add_cog(Events(bot))
